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
/// @dev Addresses for the settlement token and B20/feed pair come from .env so they can
///      be independently checked against the official Base/Chainlink sources immediately
///      before broadcast. No secret is committed to the repository.
contract DeployMainnet {
    IForgeVm internal constant VM = IForgeVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 internal constant BASE_CHAIN_ID = 8453;
    uint32 internal constant USDC_MAX_STALENESS = 2 hours;
    uint32 internal constant EQUITY_MAX_STALENESS = 6 hours;

    // 0x AllowanceHolder for Cancun-hardfork chains, including Base.
    // Source: https://docs.0x.org/docs/core-concepts/contracts
    address internal constant ALLOWANCE_HOLDER = 0x0000000000001fF3684f28c67538d4D072C22734;

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

        VM.startBroadcast(privateKey);

        registry = new AssetRegistry(deployer);
        registry.registerAsset(usdc, usdcFeed, USDC_MAX_STALENESS, false);
        registry.registerAsset(b20Token, b20Feed, EQUITY_MAX_STALENESS, true);

        factory = new StockPolicyVaultFactory(address(registry), usdc, ALLOWANCE_HOLDER);

        VM.stopBroadcast();
    }
}
