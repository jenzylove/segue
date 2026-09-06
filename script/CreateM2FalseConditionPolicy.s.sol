// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../src/interfaces/IERC20.sol";
import {StockPolicyVault} from "../src/StockPolicyVault.sol";
import {StockPolicyVaultFactory} from "../src/StockPolicyVaultFactory.sol";

interface IFalsePolicyVm {
    function envUint(string calldata name) external returns (uint256 value);
    function envAddress(string calldata name) external returns (address value);
    function addr(uint256 privateKey) external returns (address keyAddr);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Creates a deliberately false, bounded policy for B4 mainnet evidence.
/// @dev No trade is meant to happen. The follow-up read-only condition probe must
///      report CONDITION_FALSE against the deployed official Chainlink feed.
contract CreateM2FalseConditionPolicy {
    IFalsePolicyVm internal constant VM =
        IFalsePolicyVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 internal constant BASE_CHAIN_ID = 8453;
    uint256 internal constant BPS = 10_000;

    error WrongChain(uint256 actual);
    error OwnerKeyMismatch(address expected, address actual);
    error VaultOwnerMismatch(address expected, address actual);
    error FactoryVaultMismatch(address expected, address actual);
    error ActivePolicyExists(uint256 policyId);
    error UnexpectedPolicyId(uint256 expected, uint256 actual);
    error InsufficientVaultUSDC(uint256 required, uint256 actual);
    error InvalidBounds();

    function run() external returns (uint256 policyId) {
        if (block.chainid != BASE_CHAIN_ID) revert WrongChain(block.chainid);

        uint256 ownerKey = VM.envUint("DEMO_OWNER_PRIVATE_KEY");
        address owner = VM.envAddress("DEMO_OWNER_ADDRESS");
        address actualOwner = VM.addr(ownerKey);
        if (actualOwner != owner) revert OwnerKeyMismatch(owner, actualOwner);

        address vaultAddress = VM.envAddress("DEMO_VAULT_ADDRESS");
        address usdc = VM.envAddress("USDC_ADDRESS");
        address b20 = VM.envAddress("B20_TOKEN_ADDRESS");
        uint256 amount = VM.envUint("M2_BUY_USDC_ATOMIC");
        uint256 expectedPolicyId = VM.envUint("M2_FALSE_POLICY_ID");
        uint256 bufferBps = VM.envUint("M2_FALSE_TRIGGER_BUFFER_BPS");
        uint256 maxDeviationBps = VM.envUint("M2_MAX_DEVIATION_BPS");
        uint256 ttlSeconds = VM.envUint("M2_POLICY_TTL_SECONDS");

        if (
            amount == 0 || expectedPolicyId == 0 || bufferBps == 0 || bufferBps >= 5_000
                || maxDeviationBps == 0 || maxDeviationBps >= BPS || ttlSeconds < 600 || ttlSeconds > 86_400
        ) revert InvalidBounds();

        StockPolicyVault vault = StockPolicyVault(vaultAddress);
        StockPolicyVaultFactory factory =
            StockPolicyVaultFactory(VM.envAddress("FACTORY_ADDRESS"));
        if (vault.owner() != owner) revert VaultOwnerMismatch(owner, vault.owner());
        if (factory.vaultOf(owner) != vaultAddress) {
            revert FactoryVaultMismatch(vaultAddress, factory.vaultOf(owner));
        }
        if (vault.activePolicyId() != 0) revert ActivePolicyExists(vault.activePolicyId());
        if (vault.nextPolicyId() != expectedPolicyId) {
            revert UnexpectedPolicyId(expectedPolicyId, vault.nextPolicyId());
        }

        uint256 held = IERC20(usdc).balanceOf(vaultAddress);
        if (held < amount) revert InsufficientVaultUSDC(amount, held);

        // Fails closed here if the exact deployed B20 feed is stale/invalid.
        (uint256 currentPrice,) = vault.registry().priceUsd1e8(b20);
        uint256 threshold = (currentPrice * (BPS + bufferBps)) / BPS;

        StockPolicyVault.StepInput[] memory steps = new StockPolicyVault.StepInput[](1);
        steps[0] = StockPolicyVault.StepInput({
            conditionAsset: b20,
            conditionType: StockPolicyVault.ConditionType.PRICE_ABOVE,
            threshold: threshold,
            deltaBps: 0,
            sellToken: usdc,
            buyToken: b20,
            amountMode: StockPolicyVault.AmountMode.FIXED,
            amount: amount,
            maxDeviationBps: uint16(maxDeviationBps),
            expiresAt: uint40(block.timestamp + ttlSeconds)
        });

        VM.startBroadcast(ownerKey);
        policyId = vault.createPolicy(steps, amount);
        VM.stopBroadcast();

        if (policyId != expectedPolicyId) revert UnexpectedPolicyId(expectedPolicyId, policyId);
    }
}
