// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../src/interfaces/IERC20.sol";
import {StockPolicyVault} from "../src/StockPolicyVault.sol";
import {StockPolicyVaultFactory} from "../src/StockPolicyVaultFactory.sol";

interface ICreateM2PolicyVm {
    function envUint(string calldata name) external returns (uint256 value);
    function envAddress(string calldata name) external returns (address value);
    function addr(uint256 privateKey) external returns (address keyAddr);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Creates the real M2 USDC -> B20 -> USDC two-step policy.
/// @dev Policy creation itself reads the registered Chainlink feed, so run only
///      after `m2_preflight.py --require-fresh-feeds` passes.
contract CreateM2RoundTripPolicy {
    ICreateM2PolicyVm internal constant VM =
        ICreateM2PolicyVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 internal constant BASE_CHAIN_ID = 8453;
    uint256 internal constant BPS = 10_000;

    error WrongChain(uint256 actual);
    error OwnerKeyMismatch(address expected, address actual);
    error VaultOwnerMismatch(address expected, address actual);
    error VaultExecutorMismatch(address expected, address actual);
    error FactoryVaultMismatch(address expected, address actual);
    error ActivePolicyExists(uint256 policyId);
    error UnexpectedPolicyId(uint256 expected, uint256 actual);
    error InsufficientVaultUSDC(uint256 required, uint256 actual);
    error InvalidBounds();
    error InvalidCurrentPrice();

    function run() external returns (uint256 policyId) {
        if (block.chainid != BASE_CHAIN_ID) revert WrongChain(block.chainid);

        uint256 ownerKey = VM.envUint("DEMO_OWNER_PRIVATE_KEY");
        address owner = VM.envAddress("DEMO_OWNER_ADDRESS");
        if (VM.addr(ownerKey) != owner) revert OwnerKeyMismatch(owner, VM.addr(ownerKey));

        address executor = VM.envAddress("EXECUTOR_ADDRESS");
        address usdc = VM.envAddress("USDC_ADDRESS");
        address b20 = VM.envAddress("B20_TOKEN_ADDRESS");
        address vaultAddress = VM.envAddress("DEMO_VAULT_ADDRESS");
        uint256 buyAmount = VM.envUint("M2_BUY_USDC_ATOMIC");
        uint256 expectedPolicyId = VM.envUint("M2_POLICY_ID");
        uint256 triggerBufferBps = VM.envUint("M2_TRIGGER_BUFFER_BPS");
        uint256 maxDeviationBps = VM.envUint("M2_MAX_DEVIATION_BPS");
        uint256 ttlSeconds = VM.envUint("M2_POLICY_TTL_SECONDS");

        if (
            buyAmount == 0 || expectedPolicyId == 0 || triggerBufferBps == 0 || triggerBufferBps >= 5_000
                || maxDeviationBps == 0 || maxDeviationBps >= BPS || ttlSeconds < 600 || ttlSeconds > 86_400
        ) revert InvalidBounds();

        StockPolicyVault vault = StockPolicyVault(vaultAddress);
        StockPolicyVaultFactory factory =
            StockPolicyVaultFactory(VM.envAddress("FACTORY_ADDRESS"));

        if (vault.owner() != owner) revert VaultOwnerMismatch(owner, vault.owner());
        if (vault.executor() != executor) revert VaultExecutorMismatch(executor, vault.executor());
        if (factory.vaultOf(owner) != vaultAddress) {
            revert FactoryVaultMismatch(vaultAddress, factory.vaultOf(owner));
        }
        if (vault.activePolicyId() != 0) revert ActivePolicyExists(vault.activePolicyId());
        if (vault.nextPolicyId() != expectedPolicyId) {
            revert UnexpectedPolicyId(expectedPolicyId, vault.nextPolicyId());
        }

        uint256 usdcHeld = IERC20(usdc).balanceOf(vaultAddress);
        if (usdcHeld < buyAmount) revert InsufficientVaultUSDC(buyAmount, usdcHeld);

        // This call fails closed if the registered equity feed is stale/invalid.
        (uint256 currentPrice,) = vault.registry().priceUsd1e8(b20);
        if (currentPrice == 0) revert InvalidCurrentPrice();
        uint256 threshold = (currentPrice * (BPS - triggerBufferBps)) / BPS;
        if (threshold == 0) threshold = 1;

        uint40 expiresAt = uint40(block.timestamp + ttlSeconds);
        StockPolicyVault.StepInput[] memory steps = new StockPolicyVault.StepInput[](2);

        // Step 1: buy the configured official B20 with the exact tiny USDC amount.
        steps[0] = StockPolicyVault.StepInput({
            conditionAsset: b20,
            conditionType: StockPolicyVault.ConditionType.PRICE_ABOVE,
            threshold: threshold,
            deltaBps: 0,
            sellToken: usdc,
            buyToken: b20,
            amountMode: StockPolicyVault.AmountMode.FIXED,
            amount: buyAmount,
            maxDeviationBps: uint16(maxDeviationBps),
            expiresAt: expiresAt
        });

        // Step 2: only after step 1 succeeds, sell 100% of the acquired B20 back
        // to USDC through the same bounded execution target.
        steps[1] = StockPolicyVault.StepInput({
            conditionAsset: b20,
            conditionType: StockPolicyVault.ConditionType.PRICE_ABOVE,
            threshold: threshold,
            deltaBps: 0,
            sellToken: b20,
            buyToken: usdc,
            amountMode: StockPolicyVault.AmountMode.PERCENT_BALANCE,
            amount: 10_000,
            maxDeviationBps: uint16(maxDeviationBps),
            expiresAt: expiresAt
        });

        VM.startBroadcast(ownerKey);
        policyId = vault.createPolicy(steps, buyAmount);
        VM.stopBroadcast();

        if (policyId != expectedPolicyId) revert UnexpectedPolicyId(expectedPolicyId, policyId);
    }
}
