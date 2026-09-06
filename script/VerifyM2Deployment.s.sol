// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AssetRegistry} from "../src/AssetRegistry.sol";
import {StockPolicyVaultFactory} from "../src/StockPolicyVaultFactory.sol";

interface IVerifyVm {
    function envAddress(string calldata name) external returns (address value);
}

/// @notice Read-only verification of the exact M2 deployment configuration.
/// @dev Run without --broadcast. Any mismatch reverts before a demo vault is funded.
contract VerifyM2Deployment {
    IVerifyVm internal constant VM = IVerifyVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 internal constant BASE_CHAIN_ID = 8453;
    uint32 internal constant USDC_MAX_STALENESS = 2 hours;
    uint32 internal constant EQUITY_MAX_STALENESS = 6 hours;

    error WrongChain(uint256 actual);
    error MissingCode(address target);
    error ConfigMismatch(bytes32 field, address expected, address actual);
    error AssetConfigMismatch(address token);

    function run() external {
        if (block.chainid != BASE_CHAIN_ID) revert WrongChain(block.chainid);

        address registryAddress = VM.envAddress("ASSET_REGISTRY_ADDRESS");
        address factoryAddress = VM.envAddress("FACTORY_ADDRESS");
        address executor = VM.envAddress("EXECUTOR_ADDRESS");
        address usdc = VM.envAddress("USDC_ADDRESS");
        address usdcFeed = VM.envAddress("USDC_FEED_ADDRESS");
        address b20 = VM.envAddress("B20_TOKEN_ADDRESS");
        address b20Feed = VM.envAddress("B20_FEED_ADDRESS");
        address executionTarget = VM.envAddress("EXECUTION_TARGET_ADDRESS");

        if (registryAddress.code.length == 0) revert MissingCode(registryAddress);
        if (factoryAddress.code.length == 0) revert MissingCode(factoryAddress);
        if (executionTarget.code.length == 0) revert MissingCode(executionTarget);

        AssetRegistry registry = AssetRegistry(registryAddress);
        StockPolicyVaultFactory factory = StockPolicyVaultFactory(factoryAddress);

        if (registry.owner() != executor) revert ConfigMismatch("registry.owner", executor, registry.owner());
        if (factory.registry() != registryAddress) {
            revert ConfigMismatch("factory.registry", registryAddress, factory.registry());
        }
        if (factory.settlementToken() != usdc) {
            revert ConfigMismatch("factory.settlement", usdc, factory.settlementToken());
        }
        if (factory.allowanceHolder() != executionTarget) {
            revert ConfigMismatch("factory.target", executionTarget, factory.allowanceHolder());
        }

        AssetRegistry.Asset memory usdcAsset = registry.getAsset(usdc);
        if (
            usdcAsset.feed != usdcFeed || usdcAsset.maxStaleness != USDC_MAX_STALENESS || usdcAsset.isB20
                || !usdcAsset.active || !usdcAsset.exists
        ) revert AssetConfigMismatch(usdc);

        AssetRegistry.Asset memory b20Asset = registry.getAsset(b20);
        if (
            b20Asset.feed != b20Feed || b20Asset.maxStaleness != EQUITY_MAX_STALENESS || !b20Asset.isB20
                || !b20Asset.active || !b20Asset.exists
        ) revert AssetConfigMismatch(b20);
    }
}
