// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AssetRegistry} from "../src/AssetRegistry.sol";
import {StockPolicyVaultFactory} from "../src/StockPolicyVaultFactory.sol";

interface IForgeVm {
    function envUint(string calldata name) external returns (uint256 value);
    function envAddress(string calldata name) external returns (address value);
    function addr(uint256 privateKey) external returns (address keyAddr);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Base-mainnet deployment for Segue's M2 transaction proof.
/// @dev Public token/feed addresses and the execution target come from .env so they can
///      be independently checked immediately before broadcast. No secret is committed.
contract DeployMainnet {
    IForgeVm internal constant VM = IForgeVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 internal constant BASE_CHAIN_ID = 8453;
    uint32 internal constant USDC_MAX_STALENESS = 2 hours;
    uint32 internal constant EQUITY_MAX_STALENESS = 6 hours;

    error WrongChain(uint256 actual);
    error DeployerMismatch(address expected, address actual);

    function run() external returns (AssetRegistry registry, StockPolicyVaultFactory factory) {
        if (block.chainid != BASE_CHAIN_ID) revert WrongChain(block.chainid);

        uint256 privateKey = VM.envUint("EXECUTOR_PRIVATE_KEY");
        address expectedDeployer = VM.envAddress("EXECUTOR_ADDRESS");
        address deployer = VM.addr(privateKey);
        if (deployer != expectedDeployer) revert DeployerMismatch(expectedDeployer, deployer);

        address usdc = VM.envAddress("USDC_ADDRESS");
        address usdcFeed = VM.envAddress("USDC_FEED_ADDRESS");
        address b20Token = VM.envAddress("B20_TOKEN_ADDRESS");
        address b20Feed = VM.envAddress("B20_FEED_ADDRESS");
        // M2 preflight resolves this from 1inch's live /approve/spender endpoint.
        // Keeping it explicit makes the vault/factory provider-agnostic while preserving
        // an immutable, narrow execution boundary after deployment.
        address executionTarget = VM.envAddress("EXECUTION_TARGET_ADDRESS");

        VM.startBroadcast(privateKey);

        registry = new AssetRegistry(deployer);
        registry.registerAsset(usdc, usdcFeed, USDC_MAX_STALENESS, false);
        registry.registerAsset(b20Token, b20Feed, EQUITY_MAX_STALENESS, true);

        factory = new StockPolicyVaultFactory(address(registry), usdc, executionTarget);

        VM.stopBroadcast();
    }
}
