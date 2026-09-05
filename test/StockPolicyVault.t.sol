// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AssetRegistry} from "../src/AssetRegistry.sol";
import {StockPolicyVault} from "../src/StockPolicyVault.sol";
import {StockPolicyVaultFactory} from "../src/StockPolicyVaultFactory.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";

interface Vm {
    function prank(address) external;
    function startPrank(address) external;
    function stopPrank() external;
    function expectRevert() external;
    function warp(uint256) external;
}

contract MockERC20 {
    string public name;
    string public symbol;
    uint8 public immutable decimals;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory name_, string memory symbol_, uint8 decimals_) {
        name = name_;
        symbol = symbol_;
        decimals = decimals_;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "ALLOWANCE");
        if (allowed != type(uint256).max) allowance[from][msg.sender] = allowed - amount;
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "BALANCE");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
    }
}

contract MockFeed {
    uint8 public immutable decimals;
    int256 public answer;
    uint256 public updatedAt;
    uint80 public roundId = 1;

    constructor(uint8 decimals_, int256 answer_) {
        decimals = decimals_;
        setAnswer(answer_);
    }

    function setAnswer(int256 answer_) public {
        answer = answer_;
        updatedAt = block.timestamp;
        roundId += 1;
    }

    function setUpdatedAt(uint256 value) external {
        updatedAt = value;
    }

    function latestRoundData()
        external
        view
        returns (uint80, int256, uint256, uint256, uint80)
    {
        return (roundId, answer, updatedAt, updatedAt, roundId);
    }
}

contract MockAllowanceHolder {
    function swap(address sellToken, address buyToken, uint256 sellAmount, uint256 buyAmount) external {
        require(IERC20(sellToken).transferFrom(msg.sender, address(this), sellAmount), "SELL");
        require(IERC20(buyToken).transfer(msg.sender, buyAmount), "BUY");
    }
}

contract StockPolicyVaultTest {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address internal constant USER = address(0xA11CE);
    address internal constant EXECUTOR = address(0xB0B);
    address internal constant STRANGER = address(0xBAD);

    MockERC20 internal usdc;
    MockERC20 internal nvda;
    MockERC20 internal aapl;
    MockFeed internal usdcFeed;
    MockFeed internal nvdaFeed;
    MockFeed internal aaplFeed;
    MockAllowanceHolder internal router;
    AssetRegistry internal registry;
    StockPolicyVaultFactory internal factory;
    StockPolicyVault internal vault;

    uint256 internal constant ONE_USDC = 1e6;
    uint256 internal constant ONE_STOCK = 1e18;

    function setUp() public {
        vm.warp(1_800_000_000);

        usdc = new MockERC20("USDC", "USDC", 6);
        nvda = new MockERC20("NVIDIA B20", "NVDAc", 18);
        aapl = new MockERC20("Apple B20", "AAPLc", 18);

        usdcFeed = new MockFeed(8, 1e8);
        nvdaFeed = new MockFeed(8, 100e8);
        aaplFeed = new MockFeed(8, 200e8);
        router = new MockAllowanceHolder();

        registry = new AssetRegistry(address(this));
        registry.registerAsset(address(usdc), address(usdcFeed), 1 days, false);
        registry.registerAsset(address(nvda), address(nvdaFeed), 1 days, true);
        registry.registerAsset(address(aapl), address(aaplFeed), 1 days, true);

        factory = new StockPolicyVaultFactory(address(registry), address(usdc), address(router));

        vm.prank(USER);
        address vaultAddress = factory.createVault(EXECUTOR, 50 * ONE_USDC);
        vault = StockPolicyVault(vaultAddress);

        usdc.mint(USER, 100 * ONE_USDC);
        nvda.mint(address(router), 100 * ONE_STOCK);
        aapl.mint(address(router), 100 * ONE_STOCK);

        vm.startPrank(USER);
        usdc.approve(address(vault), 100 * ONE_USDC);
        vault.depositSettlement(50 * ONE_USDC);
        vm.stopPrank();
    }

    function test_factoryCreatesIsolatedVaults() public {
        address other = address(0xCAFE);
        vm.prank(other);
        address second = factory.createVault(EXECUTOR, 10 * ONE_USDC);
        require(second != address(vault), "same vault");
        require(factory.vaultOf(USER) == address(vault), "user lookup");
        require(factory.vaultOf(other) == second, "other lookup");
        require(factory.isVault(second), "not recognized");
    }

    function test_createPolicyActivatesOnlyFirstStep() public {
        uint256 policyId = _createTwoStepPolicy();
        (StockPolicyVault.PolicyStatus status,, uint8 currentStep, uint8 stepCount,,) = vault.policies(policyId);
        require(status == StockPolicyVault.PolicyStatus.LIVE, "not live");
        require(currentStep == 0 && stepCount == 2, "bad policy cursor");

        StockPolicyVault.Step memory first = vault.getStep(policyId, 0);
        StockPolicyVault.Step memory second = vault.getStep(policyId, 1);
        require(first.status == StockPolicyVault.StepStatus.ACTIVE, "first not active");
        require(second.status == StockPolicyVault.StepStatus.QUEUED, "second not queued");
        require(first.referencePrice == 100e8, "first reference");
        require(second.referencePrice == 0, "queued got reference");
    }

    function test_executeBuyAdvancesAndCapturesNextReference() public {
        uint256 policyId = _createTwoStepPolicy();
        bytes memory data = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(usdc), address(nvda), 10 * ONE_USDC, ONE_STOCK / 10)
        );

        vm.prank(EXECUTOR);
        vault.executeStep(policyId, data);

        StockPolicyVault.Step memory first = vault.getStep(policyId, 0);
        StockPolicyVault.Step memory second = vault.getStep(policyId, 1);
        require(first.status == StockPolicyVault.StepStatus.EXECUTED, "first not executed");
        require(second.status == StockPolicyVault.StepStatus.ACTIVE, "second not active");
        require(second.referencePrice == 100e8, "next reference not captured");
        require(nvda.balanceOf(address(vault)) == ONE_STOCK / 10, "stock not in vault");
        require(vault.vaultDeployedUSDC() == 10 * ONE_USDC, "vault exposure");

        (StockPolicyVault.PolicyStatus status,, uint8 currentStep,,, uint256 deployed) = vault.policies(policyId);
        require(status == StockPolicyVault.PolicyStatus.LIVE && currentStep == 1, "did not advance");
        require(deployed == 10 * ONE_USDC, "policy exposure");
    }

    function test_secondStepCannotExecuteBeforeFirst() public {
        uint256 policyId = _createTwoStepPolicy();
        StockPolicyVault.Step memory second = vault.getStep(policyId, 1);
        require(second.status == StockPolicyVault.StepStatus.QUEUED, "not queued");

        bytes memory wrong = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(nvda), address(usdc), ONE_STOCK / 20, 5 * ONE_USDC)
        );
        vm.expectRevert();
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, wrong);
    }

    function test_relativeConditionBlocksUntilPriceMoves() public {
        uint256 policyId = _createTwoStepPolicy();
        _executeFirst(policyId);

        (bool executable, StockPolicyVault.PreviewReason reason,,,) = vault.previewExecution(policyId);
        require(!executable, "executed too early");
        require(reason == StockPolicyVault.PreviewReason.CONDITION_FALSE, "wrong reason");

        nvdaFeed.setAnswer(110e8);
        (executable, reason,,,) = vault.previewExecution(policyId);
        require(executable, "should be ready");
        require(reason == StockPolicyVault.PreviewReason.READY, "not ready");
    }

    function test_buyThenSellClosesPolicyAndReleasesOnlyItsExposure() public {
        uint256 policyId = _createTwoStepPolicy();
        _executeFirst(policyId);

        nvdaFeed.setAnswer(110e8);
        bytes memory data = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(nvda), address(usdc), ONE_STOCK / 20, 5_500_000)
        );
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, data);

        (StockPolicyVault.PolicyStatus status,,,,, uint256 deployed) = vault.policies(policyId);
        require(status == StockPolicyVault.PolicyStatus.COMPLETED, "not completed");
        require(vault.activePolicyId() == 0, "active id not cleared");
        require(deployed == 4_500_000, "policy exposure accounting");
        require(vault.vaultDeployedUSDC() == 4_500_000, "vault exposure accounting");
    }

    function test_routerCannotSpendMoreThanStoredStepAmount() public {
        uint256 policyId = _createTwoStepPolicy();
        uint256 usdcBefore = usdc.balanceOf(address(vault));

        bytes memory malicious = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(usdc), address(nvda), 11 * ONE_USDC, ONE_STOCK / 10)
        );
        vm.expectRevert();
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, malicious);

        require(usdc.balanceOf(address(vault)) == usdcBefore, "funds moved");
        require(usdc.allowance(address(vault), address(router)) == 0, "allowance persisted");
    }

    function test_unsafeOracleDeviationRevertsEntireSwap() public {
        uint256 policyId = _createTwoStepPolicy();
        uint256 usdcBefore = usdc.balanceOf(address(vault));
        uint256 stockBefore = nvda.balanceOf(address(vault));

        bytes memory badOutput = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(usdc), address(nvda), 10 * ONE_USDC, ONE_STOCK / 20)
        );
        vm.expectRevert();
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, badOutput);

        require(usdc.balanceOf(address(vault)) == usdcBefore, "sell not reverted");
        require(nvda.balanceOf(address(vault)) == stockBefore, "buy not reverted");
    }

    function test_capsPauseCancelAndUnauthorizedWithdrawFailSafely() public {
        StockPolicyVault.StepInput[] memory steps = new StockPolicyVault.StepInput[](1);
        steps[0] = _buyStep(30 * ONE_USDC);

        vm.prank(USER);
        uint256 policyId = vault.createPolicy(steps, 20 * ONE_USDC);

        (bool executable, StockPolicyVault.PreviewReason reason,,,) = vault.previewExecution(policyId);
        require(!executable && reason == StockPolicyVault.PreviewReason.POLICY_CAP, "policy cap ignored");

        vm.prank(USER);
        vault.setPaused(true);
        (executable, reason,,,) = vault.previewExecution(policyId);
        require(!executable && reason == StockPolicyVault.PreviewReason.PAUSED, "pause ignored");

        vm.expectRevert();
        vm.prank(STRANGER);
        vault.withdraw(address(usdc), STRANGER, ONE_USDC);

        vm.prank(USER);
        vault.setPaused(false);
        vm.prank(USER);
        vault.cancelPolicy(policyId);

        (StockPolicyVault.PolicyStatus status,,,,,) = vault.policies(policyId);
        require(status == StockPolicyVault.PolicyStatus.CANCELLED, "not cancelled");
    }

    function test_staleFeedPreventsExecution() public {
        uint256 policyId = _createTwoStepPolicy();
        vm.warp(block.timestamp + 2 days);

        vm.expectRevert();
        vault.previewExecution(policyId);
    }

    function test_completedStepCannotExecuteTwice() public {
        uint256 policyId = _createOneStepPolicy();
        bytes memory data = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(usdc), address(nvda), 10 * ONE_USDC, ONE_STOCK / 10)
        );
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, data);

        vm.expectRevert();
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, data);
    }

    function _createOneStepPolicy() internal returns (uint256) {
        StockPolicyVault.StepInput[] memory steps = new StockPolicyVault.StepInput[](1);
        steps[0] = _buyStep(10 * ONE_USDC);
        vm.prank(USER);
        return vault.createPolicy(steps, 20 * ONE_USDC);
    }

    function _createTwoStepPolicy() internal returns (uint256) {
        StockPolicyVault.StepInput[] memory steps = new StockPolicyVault.StepInput[](2);
        steps[0] = _buyStep(10 * ONE_USDC);
        steps[1] = StockPolicyVault.StepInput({
            conditionAsset: address(nvda),
            conditionType: StockPolicyVault.ConditionType.UP_BPS_FROM_REFERENCE,
            threshold: 0,
            deltaBps: 1_000,
            sellToken: address(nvda),
            buyToken: address(usdc),
            amountMode: StockPolicyVault.AmountMode.PERCENT_BALANCE,
            amount: 5_000,
            maxDeviationBps: 100,
            expiresAt: 0
        });

        vm.prank(USER);
        return vault.createPolicy(steps, 20 * ONE_USDC);
    }

    function _buyStep(uint256 amount) internal view returns (StockPolicyVault.StepInput memory) {
        return StockPolicyVault.StepInput({
            conditionAsset: address(nvda),
            conditionType: StockPolicyVault.ConditionType.PRICE_BELOW,
            threshold: 150e8,
            deltaBps: 0,
            sellToken: address(usdc),
            buyToken: address(nvda),
            amountMode: StockPolicyVault.AmountMode.FIXED,
            amount: amount,
            maxDeviationBps: 100,
            expiresAt: 0
        });
    }

    function _executeFirst(uint256 policyId) internal {
        bytes memory data = abi.encodeCall(
            MockAllowanceHolder.swap,
            (address(usdc), address(nvda), 10 * ONE_USDC, ONE_STOCK / 10)
        );
        vm.prank(EXECUTOR);
        vault.executeStep(policyId, data);
    }
}
