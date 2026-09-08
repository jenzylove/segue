// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {StockPolicyVaultTest, MockAllowanceHolder} from "./StockPolicyVault.t.sol";
import {StockPolicyVault} from "../src/StockPolicyVault.sol";
import {PrepareM2Vault} from "../script/PrepareM2Vault.s.sol";
import {CreateM2RoundTripPolicy} from "../script/CreateM2RoundTripPolicy.s.sol";
import {CreateM2FalseConditionPolicy} from "../script/CreateM2FalseConditionPolicy.s.sol";
import {ExecuteM2Quote} from "../script/ExecuteM2Quote.s.sol";
import {CancelM2FalsePolicy} from "../script/CancelM2FalsePolicy.s.sol";

interface IM2TestVm {
    function setEnv(string calldata key, string calldata value) external;
    function addr(uint256 key) external returns (address);
    function toString(address value) external returns (string memory);
    function toString(bytes calldata value) external returns (string memory);
    function chainId(uint256 value) external;
}

contract M2ScriptsTest is StockPolicyVaultTest {
    IM2TestVm constant config = IM2TestVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address internal constant TEST_OWNER = 0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf;
    address internal constant TEST_EXECUTOR = 0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF;

    function configure() internal returns (address owner) {
        config.chainId(8453); // Local EVM only; never an RPC fork or mainnet evidence.
        owner = TEST_OWNER; // Public, test-only key 1.
        config.setEnv("DEMO_OWNER_PRIVATE_KEY", "1");
        config.setEnv("EXECUTOR_PRIVATE_KEY", "2");
        config.setEnv("DEMO_OWNER_ADDRESS", config.toString(owner));
        config.setEnv("EXECUTOR_ADDRESS", config.toString(TEST_EXECUTOR));
        config.setEnv("FACTORY_ADDRESS", config.toString(address(factory)));
        config.setEnv("USDC_ADDRESS", config.toString(address(usdc)));
        config.setEnv("B20_TOKEN_ADDRESS", config.toString(address(nvda)));
        config.setEnv("EXECUTION_TARGET_ADDRESS", config.toString(address(router)));
        config.setEnv("BASE_BUILDER_CODE", "test-only");
        config.setEnv("M2_BUY_USDC_ATOMIC", "1000000");
        config.setEnv("M2_POLICY_ID", "1");
        config.setEnv("M2_FALSE_POLICY_ID", "2");
        config.setEnv("M2_TRIGGER_BUFFER_BPS", "500");
        config.setEnv("M2_FALSE_TRIGGER_BUFFER_BPS", "500");
        config.setEnv("M2_MAX_DEVIATION_BPS", "500");
        config.setEnv("M2_POLICY_TTL_SECONDS", "3600");
        config.setEnv("M2_FALSE_POLICY_TTL_SECONDS", "86400");
    }

    function test_runbookScriptsRoundTripAndFalseProbeAfterLoss() public {
        address owner = configure();
        usdc.mint(owner, ONE_USDC);
        address demo = (new PrepareM2Vault()).run();
        config.setEnv("DEMO_VAULT_ADDRESS", config.toString(demo));
        require(StockPolicyVault(demo).owner() == owner, "owner changed by attribution");
        require((new CreateM2RoundTripPolicy()).run() == 1, "policy id");
        bytes memory buy =
            abi.encodeCall(MockAllowanceHolder.swap, (address(usdc), address(nvda), ONE_USDC, ONE_STOCK / 100));
        config.setEnv("M2_ROUTE_CALLDATA", config.toString(buy));
        (new ExecuteM2Quote()).run();
        bytes memory sell =
            abi.encodeCall(MockAllowanceHolder.swap, (address(nvda), address(usdc), ONE_STOCK / 100, 990_000));
        config.setEnv("M2_ROUTE_CALLDATA", config.toString(sell));
        (new ExecuteM2Quote()).run();
        require(usdc.balanceOf(demo) == 990_000, "loss fixture missing");
        require((new CreateM2FalseConditionPolicy()).run() == 2, "false policy failed after loss");
        (bool executable, StockPolicyVault.PreviewReason reason,,,) = StockPolicyVault(demo).previewExecution(2);
        require(!executable && reason == StockPolicyVault.PreviewReason.CONDITION_FALSE, "false proof");
        (new CancelM2FalsePolicy()).run();
        require(StockPolicyVault(demo).activePolicyId() == 0, "cancel failed");
    }

}
