// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {M2Attribution} from "./M2Attribution.sol";

import {IERC20} from "../src/interfaces/IERC20.sol";
import {StockPolicyVault} from "../src/StockPolicyVault.sol";
import {StockPolicyVaultFactory} from "../src/StockPolicyVaultFactory.sol";

interface IPrepareM2Vm {
    function envUint(string calldata name) external returns (uint256 value);
    function envAddress(string calldata name) external returns (address value);
    function addr(uint256 privateKey) external returns (address keyAddr);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Creates/funds the tiny M2 user vault without making the automation
///         executor the owner of strategy funds.
/// @dev Safe to run while the equity feed is stale: no policy/price read happens here.
contract PrepareM2Vault {
    IPrepareM2Vm internal constant VM = IPrepareM2Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 internal constant BASE_CHAIN_ID = 8453;

    error WrongChain(uint256 actual);
    error OwnerKeyMismatch(address expected, address actual);
    error FactorySettlementMismatch(address expected, address actual);
    error VaultOwnerMismatch(address expected, address actual);
    error VaultExecutorMismatch(address expected, address actual);
    error VaultLimitTooSmall(uint256 required, uint256 actual);
    error InsufficientOwnerUSDC(uint256 required, uint256 actual);
    error InvalidAmount();
    error OwnerIsExecutor();
    error TokenApprovalFailed();

    function run() external returns (address vaultAddress) {
        if (block.chainid != BASE_CHAIN_ID) revert WrongChain(block.chainid);
        bytes memory attribution = M2Attribution.configuredSuffix();

        uint256 ownerKey = VM.envUint("DEMO_OWNER_PRIVATE_KEY");
        address expectedOwner = VM.envAddress("DEMO_OWNER_ADDRESS");
        address actualOwner = VM.addr(ownerKey);
        if (actualOwner != expectedOwner) revert OwnerKeyMismatch(expectedOwner, actualOwner);

        address executor = VM.envAddress("EXECUTOR_ADDRESS");
        if (executor == expectedOwner) revert OwnerIsExecutor();
        address usdc = VM.envAddress("USDC_ADDRESS");
        uint256 requiredUSDC = VM.envUint("M2_BUY_USDC_ATOMIC");
        if (requiredUSDC == 0) revert InvalidAmount();

        StockPolicyVaultFactory factory = StockPolicyVaultFactory(VM.envAddress("FACTORY_ADDRESS"));
        if (factory.settlementToken() != usdc) {
            revert FactorySettlementMismatch(usdc, factory.settlementToken());
        }

        vaultAddress = factory.vaultOf(expectedOwner);
        if (vaultAddress == address(0)) {
            VM.startBroadcast(ownerKey);
            vaultAddress = abi.decode(
                M2Attribution.callWithSuffix(
                    address(factory),
                    abi.encodeCall(StockPolicyVaultFactory.createVault, (executor, requiredUSDC)),
                    attribution
                ),
                (address)
            );
            VM.stopBroadcast();
        }

        StockPolicyVault vault = StockPolicyVault(vaultAddress);
        if (vault.owner() != expectedOwner) revert VaultOwnerMismatch(expectedOwner, vault.owner());
        if (vault.executor() != executor) revert VaultExecutorMismatch(executor, vault.executor());
        if (vault.vaultMaxDeployedUSDC() < requiredUSDC) {
            revert VaultLimitTooSmall(requiredUSDC, vault.vaultMaxDeployedUSDC());
        }

        uint256 held = IERC20(usdc).balanceOf(vaultAddress);
        if (held < requiredUSDC) {
            uint256 needed = requiredUSDC - held;
            uint256 ownerBalance = IERC20(usdc).balanceOf(expectedOwner);
            if (ownerBalance < needed) revert InsufficientOwnerUSDC(needed, ownerBalance);

            VM.startBroadcast(ownerKey);
            if (!abi.decode(
                    M2Attribution.callWithSuffix(usdc, abi.encodeCall(IERC20.approve, (vaultAddress, 0)), attribution),
                    (bool)
                )) revert TokenApprovalFailed();
            if (!abi.decode(
                    M2Attribution.callWithSuffix(
                        usdc, abi.encodeCall(IERC20.approve, (vaultAddress, needed)), attribution
                    ),
                    (bool)
                )) revert TokenApprovalFailed();
            M2Attribution.callWithSuffix(
                address(vault), abi.encodeCall(StockPolicyVault.depositSettlement, (needed)), attribution
            );
            VM.stopBroadcast();
        }
    }
}
