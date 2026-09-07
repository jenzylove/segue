// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {M2Attribution} from "../script/M2Attribution.sol";
import {StockPolicyVaultTest, MockAllowanceHolder} from "./StockPolicyVault.t.sol";
import {StockPolicyVault} from "../src/StockPolicyVault.sol";

contract M2AttributionTest is StockPolicyVaultTest {
    function test_suffixMatchesOxSchemaZeroVector() public pure {
        require(
            keccak256(M2Attribution.suffix("baseapp"))
                == keccak256(hex"62617365617070070080218021802180218021802180218021"),
            "wrong encoding"
        );
    }

    function encodeSuffix(string memory code) external pure returns (bytes memory) {
        return M2Attribution.suffix(code);
    }

    function test_invalidBuilderCodeRejected() public {
        vm.expectRevert();
        this.encodeSuffix("");
        vm.expectRevert();
        this.encodeSuffix("one,two");
        vm.expectRevert();
        this.encodeSuffix("has space");
    }

    function test_attributedVaultExecutionPreservesCallerAndBounds() public {
        uint256 id = _createOneStepPolicy();
        bytes memory route =
            abi.encodeCall(MockAllowanceHolder.swap, (address(usdc), address(nvda), 10 * ONE_USDC, ONE_STOCK / 10));
        bytes memory suffix = M2Attribution.suffix("test-only");
        vm.prank(EXECUTOR);
        M2Attribution.callWithSuffix(address(vault), abi.encodeCall(StockPolicyVault.executeStep, (id, route)), suffix);
        require(vault.activePolicyId() == 0, "policy not completed");
        require(nvda.balanceOf(address(vault)) == ONE_STOCK / 10, "wrong output");
        require(usdc.allowance(address(vault), address(router)) == 0, "allowance remains");
    }

    function test_attributedUnauthorizedWithdrawalStillReverts() public {
        bytes memory suffix = M2Attribution.suffix("test-only");
        vm.expectRevert();
        vm.prank(EXECUTOR);
        M2Attribution.callWithSuffix(
            address(vault), abi.encodeCall(StockPolicyVault.withdraw, (address(usdc), EXECUTOR, ONE_USDC)), suffix
        );
    }
}
