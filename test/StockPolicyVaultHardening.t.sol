// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {StockPolicyVaultTest, MockAllowanceHolder} from "./StockPolicyVault.t.sol";
import {StockPolicyVault} from "../src/StockPolicyVault.sol";

contract StockPolicyVaultHardeningTest is StockPolicyVaultTest {
    function test_executorCannotAdvanceWithPartialSellEvenIfItOverpaysOutput() public {
        uint256 policyId = _createOneStepPolicy();
        uint256 usdcBefore = usdc.balanceOf(address(vault));
        uint256 stockBefore = nvda.balanceOf(address(vault));

        // The stored rule requires exactly 10 USDC. An untrusted executor must not be
        // able to sell only 9 USDC, donate enough NVDA to satisfy the output guard,
        // and thereby advance the state machine.
        bytes memory partial = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(usdc), address(nvda), 9 * ONE_USDC, ONE_STOCK / 10)
        );

        vm.expectRevert();
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, partial);

        require(usdc.balanceOf(address(vault)) == usdcBefore, "partial sell moved USDC");
        require(nvda.balanceOf(address(vault)) == stockBefore, "partial sell moved stock");
        StockPolicyVault.Step memory step = vault.getStep(policyId, 0);
        require(step.status == StockPolicyVault.StepStatus.ACTIVE, "partial sell advanced step");
    }

    function test_laterPolicySellReleasesVaultWidePriorExposure() public {
        uint256 buyPolicy = _createOneStepPolicy();
        bytes memory buyData = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(usdc), address(nvda), 10 * ONE_USDC, ONE_STOCK / 10)
        );
        vm.prank(EXECUTOR);
        vault.executeStep(buyPolicy, buyData);
        require(vault.vaultDeployedUSDC() == 10 * ONE_USDC, "buy exposure missing");

        StockPolicyVault.StepInput[] memory steps = new StockPolicyVault.StepInput[](1);
        steps[0] = StockPolicyVault.StepInput({
            conditionAsset: address(nvda),
            conditionType: StockPolicyVault.ConditionType.PRICE_ABOVE,
            threshold: 1,
            deltaBps: 0,
            sellToken: address(nvda),
            buyToken: address(usdc),
            amountMode: StockPolicyVault.AmountMode.FIXED,
            amount: ONE_STOCK / 20,
            maxDeviationBps: 100,
            expiresAt: 0
        });

        vm.prank(USER);
        uint256 sellPolicy = vault.createPolicy(steps, 20 * ONE_USDC);
        bytes memory sellData = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(nvda), address(usdc), ONE_STOCK / 20, 5_500_000)
        );
        vm.prank(EXECUTOR);
        vault.executeStep(sellPolicy, sellData);

        // The new policy began with zero policy-local deployed USDC, but the sale
        // returned capital from stock bought by the previous policy. The vault-wide
        // exposure must therefore fall from 10 to 4.5 USDC.
        require(vault.vaultDeployedUSDC() == 4_500_000, "prior exposure not released");
    }
}
