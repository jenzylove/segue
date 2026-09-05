// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {AssetRegistry} from "./AssetRegistry.sol";

/// @notice User-owned bounded execution vault for Segue stock policies.
/// @dev The executor may only attempt the exact active step. The vault rechecks the
///      Chainlink-backed condition, token pair, amount, price-deviation guard, caps,
///      and one-time state transition before accepting an execution.
contract StockPolicyVault {
    uint16 public constant BPS = 10_000;
    uint8 public constant MAX_STEPS = 8;

    enum ConditionType {
        PRICE_ABOVE,
        PRICE_BELOW,
        UP_BPS_FROM_REFERENCE,
        DOWN_BPS_FROM_REFERENCE
    }

    enum AmountMode {
        FIXED,
        PERCENT_BALANCE
    }

    enum PolicyStatus {
        NONE,
        LIVE,
        COMPLETED,
        CANCELLED
    }

    enum StepStatus {
        NONE,
        QUEUED,
        ACTIVE,
        EXECUTED,
        CANCELLED
    }

    enum PreviewReason {
        READY,
        PAUSED,
        POLICY_INACTIVE,
        STEP_INACTIVE,
        EXPIRED,
        CONDITION_FALSE,
        ZERO_SELL,
        INSUFFICIENT_BALANCE,
        POLICY_CAP,
        VAULT_CAP
    }

    struct Policy {
        PolicyStatus status;
        uint40 createdAt;
        uint8 currentStep;
        uint8 stepCount;
        uint256 maxDeployedUSDC;
        uint256 deployedUSDC;
    }

    struct Step {
        StepStatus status;
        address conditionAsset;
        ConditionType conditionType;
        uint256 threshold;
        uint16 deltaBps;
        uint256 referencePrice;
        address sellToken;
        address buyToken;
        AmountMode amountMode;
        uint256 amount;
        uint16 maxDeviationBps;
        uint40 expiresAt;
    }

    struct StepInput {
        address conditionAsset;
        ConditionType conditionType;
        uint256 threshold;
        uint16 deltaBps;
        address sellToken;
        address buyToken;
        AmountMode amountMode;
        uint256 amount;
        uint16 maxDeviationBps;
        uint40 expiresAt;
    }

    error NotOwner();
    error NotExecutorOrOwner();
    error ZeroAddress();
    error InvalidLimit();
    error ActivePolicyExists(uint256 policyId);
    error InvalidStepCount();
    error InvalidStep(uint256 stepIndex);
    error UnsupportedAsset(address token);
    error SettlementPairRequired(address sellToken, address buyToken);
    error PolicyNotLive(uint256 policyId);
    error VaultPaused();
    error ExecutionNotReady(PreviewReason reason);
    error RouterCallFailed(bytes data);
    error UnsafeOutput(uint256 received, uint256 minimumRequired);
    error InvalidSellDelta(uint256 sold, uint256 required);
    error Reentrancy();
    error TokenCallFailed(address token, bytes data);

    event Deposited(address indexed token, uint256 amount);
    event Withdrawn(address indexed token, address indexed to, uint256 amount);
    event ExecutorSet(address indexed previousExecutor, address indexed newExecutor);
    event VaultLimitSet(uint256 previousLimit, uint256 newLimit);
    event PausedSet(bool paused);
    event PolicyCreated(uint256 indexed policyId, uint8 stepCount, uint256 maxDeployedUSDC);
    event StepActivated(uint256 indexed policyId, uint8 indexed stepIndex, uint256 referencePrice);
    event ExecutionAttempted(
        uint256 indexed policyId,
        uint8 indexed stepIndex,
        address sellToken,
        address buyToken,
        uint256 sellAmount
    );
    event StepExecuted(
        uint256 indexed policyId,
        uint8 indexed stepIndex,
        uint256 soldAmount,
        uint256 boughtAmount,
        uint256 minBuyAmount
    );
    event PolicyCompleted(uint256 indexed policyId);
    event PolicyCancelled(uint256 indexed policyId);

    address public immutable owner;
    address public executor;
    AssetRegistry public immutable registry;
    address public immutable settlementToken;
    address public immutable allowanceHolder;

    bool public paused;
    uint256 public vaultMaxDeployedUSDC;
    uint256 public vaultDeployedUSDC;
    uint256 public nextPolicyId = 1;
    uint256 public activePolicyId;

    mapping(uint256 policyId => Policy policy) public policies;
    mapping(uint256 policyId => mapping(uint8 stepIndex => Step step)) private _steps;

    uint256 private _entered;

    constructor(
        address owner_,
        address executor_,
        address registry_,
        address settlementToken_,
        address allowanceHolder_,
        uint256 maxDeployedUSDC_
    ) {
        if (
            owner_ == address(0) || executor_ == address(0) || registry_ == address(0)
                || settlementToken_ == address(0) || allowanceHolder_ == address(0)
        ) revert ZeroAddress();
        if (maxDeployedUSDC_ == 0) revert InvalidLimit();

        owner = owner_;
        executor = executor_;
        registry = AssetRegistry(registry_);
        settlementToken = settlementToken_;
        allowanceHolder = allowanceHolder_;
        vaultMaxDeployedUSDC = maxDeployedUSDC_;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyExecutorOrOwner() {
        if (msg.sender != executor && msg.sender != owner) revert NotExecutorOrOwner();
        _;
    }

    modifier nonReentrant() {
        if (_entered == 1) revert Reentrancy();
        _entered = 1;
        _;
        _entered = 0;
    }

    function setExecutor(address newExecutor) external onlyOwner {
        if (newExecutor == address(0)) revert ZeroAddress();
        address previous = executor;
        executor = newExecutor;
        emit ExecutorSet(previous, newExecutor);
    }

    function setVaultMaxDeployedUSDC(uint256 newLimit) external onlyOwner {
        if (newLimit == 0 || newLimit < vaultDeployedUSDC) revert InvalidLimit();
        uint256 previous = vaultMaxDeployedUSDC;
        vaultMaxDeployedUSDC = newLimit;
        emit VaultLimitSet(previous, newLimit);
    }

    function setPaused(bool value) external onlyOwner {
        paused = value;
        emit PausedSet(value);
    }

    function depositSettlement(uint256 amount) external nonReentrant onlyOwner {
        if (amount == 0) revert InvalidLimit();
        _safeTransferFrom(settlementToken, msg.sender, address(this), amount);
        emit Deposited(settlementToken, amount);
    }

    /// @notice Owner-controlled recovery. A withdrawal may make a future step non-executable,
    ///         but can never make the worker exceed the stored rules.
    function withdraw(address token, address to, uint256 amount) external nonReentrant onlyOwner {
        if (to == address(0)) revert ZeroAddress();
        _safeTransfer(token, to, amount);
        emit Withdrawn(token, to, amount);
    }

    function createPolicy(StepInput[] calldata inputs, uint256 policyMaxDeployedUSDC)
        external
        onlyOwner
        returns (uint256 policyId)
    {
        if (paused) revert VaultPaused();
        if (activePolicyId != 0) revert ActivePolicyExists(activePolicyId);
        if (inputs.length == 0 || inputs.length > MAX_STEPS) revert InvalidStepCount();
        if (policyMaxDeployedUSDC == 0 || policyMaxDeployedUSDC > vaultMaxDeployedUSDC) revert InvalidLimit();

        policyId = nextPolicyId++;
        Policy storage policy = policies[policyId];
        policy.status = PolicyStatus.LIVE;
        policy.createdAt = uint40(block.timestamp);
        policy.currentStep = 0;
        policy.stepCount = uint8(inputs.length);
        policy.maxDeployedUSDC = policyMaxDeployedUSDC;
        activePolicyId = policyId;

        for (uint8 i = 0; i < inputs.length; ++i) {
            _validateStep(inputs[i], i);
            Step storage step = _steps[policyId][i];
            step.status = i == 0 ? StepStatus.ACTIVE : StepStatus.QUEUED;
            step.conditionAsset = inputs[i].conditionAsset;
            step.conditionType = inputs[i].conditionType;
            step.threshold = inputs[i].threshold;
            step.deltaBps = inputs[i].deltaBps;
            step.sellToken = inputs[i].sellToken;
            step.buyToken = inputs[i].buyToken;
            step.amountMode = inputs[i].amountMode;
            step.amount = inputs[i].amount;
            step.maxDeviationBps = inputs[i].maxDeviationBps;
            step.expiresAt = inputs[i].expiresAt;
        }

        uint256 referencePrice = _captureReference(policyId, 0);
        emit PolicyCreated(policyId, uint8(inputs.length), policyMaxDeployedUSDC);
        emit StepActivated(policyId, 0, referencePrice);
    }

    function cancelPolicy(uint256 policyId) external onlyOwner {
        Policy storage policy = policies[policyId];
        if (policy.status != PolicyStatus.LIVE || activePolicyId != policyId) revert PolicyNotLive(policyId);

        policy.status = PolicyStatus.CANCELLED;
        for (uint8 i = policy.currentStep; i < policy.stepCount; ++i) {
            Step storage step = _steps[policyId][i];
            if (step.status == StepStatus.ACTIVE || step.status == StepStatus.QUEUED) {
                step.status = StepStatus.CANCELLED;
            }
        }
        activePolicyId = 0;
        emit PolicyCancelled(policyId);
    }

    function getStep(uint256 policyId, uint8 stepIndex) external view returns (Step memory) {
        return _steps[policyId][stepIndex];
    }

    function previewExecution(uint256 policyId)
        public
        view
        returns (
            bool executable,
            PreviewReason reason,
            uint256 currentPrice,
            uint256 sellAmount,
            uint256 minBuyAmount
        )
    {
        if (paused) return (false, PreviewReason.PAUSED, 0, 0, 0);

        Policy memory policy = policies[policyId];
        if (policy.status != PolicyStatus.LIVE || activePolicyId != policyId) {
            return (false, PreviewReason.POLICY_INACTIVE, 0, 0, 0);
        }

        Step memory step = _steps[policyId][policy.currentStep];
        if (step.status != StepStatus.ACTIVE) {
            return (false, PreviewReason.STEP_INACTIVE, 0, 0, 0);
        }
        if (step.expiresAt != 0 && block.timestamp > step.expiresAt) {
            return (false, PreviewReason.EXPIRED, 0, 0, 0);
        }

        (currentPrice,) = registry.priceUsd1e8(step.conditionAsset);
        if (!_conditionMet(step, currentPrice)) {
            return (false, PreviewReason.CONDITION_FALSE, currentPrice, 0, 0);
        }

        sellAmount = _resolveSellAmount(step);
        if (sellAmount == 0) return (false, PreviewReason.ZERO_SELL, currentPrice, 0, 0);

        uint256 balance = IERC20(step.sellToken).balanceOf(address(this));
        if (balance < sellAmount) {
            return (false, PreviewReason.INSUFFICIENT_BALANCE, currentPrice, sellAmount, 0);
        }

        if (step.sellToken == settlementToken) {
            if (policy.deployedUSDC + sellAmount > policy.maxDeployedUSDC) {
                return (false, PreviewReason.POLICY_CAP, currentPrice, sellAmount, 0);
            }
            if (vaultDeployedUSDC + sellAmount > vaultMaxDeployedUSDC) {
                return (false, PreviewReason.VAULT_CAP, currentPrice, sellAmount, 0);
            }
        }

        minBuyAmount = _minimumBuyAmount(step.sellToken, step.buyToken, sellAmount, step.maxDeviationBps);
        return (true, PreviewReason.READY, currentPrice, sellAmount, minBuyAmount);
    }

    function executeStep(uint256 policyId, bytes calldata allowanceHolderCalldata)
        external
        nonReentrant
        onlyExecutorOrOwner
    {
        (bool executable, PreviewReason reason,, uint256 sellAmount, uint256 minBuyAmount) = previewExecution(policyId);
        if (!executable) revert ExecutionNotReady(reason);

        Policy storage policy = policies[policyId];
        uint8 stepIndex = policy.currentStep;
        Step storage step = _steps[policyId][stepIndex];

        uint256 sellBefore = IERC20(step.sellToken).balanceOf(address(this));
        uint256 buyBefore = IERC20(step.buyToken).balanceOf(address(this));

        _safeApprove(step.sellToken, allowanceHolder, 0);
        _safeApprove(step.sellToken, allowanceHolder, sellAmount);

        emit ExecutionAttempted(policyId, stepIndex, step.sellToken, step.buyToken, sellAmount);

        (bool ok, bytes memory result) = allowanceHolder.call(allowanceHolderCalldata);
        if (!ok) revert RouterCallFailed(result);

        _safeApprove(step.sellToken, allowanceHolder, 0);

        uint256 sellAfter = IERC20(step.sellToken).balanceOf(address(this));
        uint256 buyAfter = IERC20(step.buyToken).balanceOf(address(this));
        if (sellAfter > sellBefore || buyAfter < buyBefore) revert InvalidSellDelta(0, sellAmount);

        uint256 sold = sellBefore - sellAfter;
        uint256 bought = buyAfter - buyBefore;
        // A worker may choose the route, but it may not advance a step by selling less
        // than the exact amount resolved from the user's stored rule.
        if (sold != sellAmount) revert InvalidSellDelta(sold, sellAmount);
        if (bought < minBuyAmount) revert UnsafeOutput(bought, minBuyAmount);

        if (step.sellToken == settlementToken) {
            policy.deployedUSDC += sold;
            vaultDeployedUSDC += sold;
        } else if (step.buyToken == settlementToken) {
            uint256 policyReduction = bought > policy.deployedUSDC ? policy.deployedUSDC : bought;
            uint256 vaultReduction = bought > vaultDeployedUSDC ? vaultDeployedUSDC : bought;
            policy.deployedUSDC -= policyReduction;
            vaultDeployedUSDC -= vaultReduction;
        }

        step.status = StepStatus.EXECUTED;
        emit StepExecuted(policyId, stepIndex, sold, bought, minBuyAmount);

        uint8 next = stepIndex + 1;
        if (next < policy.stepCount) {
            policy.currentStep = next;
            Step storage nextStep = _steps[policyId][next];
            nextStep.status = StepStatus.ACTIVE;
            uint256 referencePrice = _captureReference(policyId, next);
            emit StepActivated(policyId, next, referencePrice);
        } else {
            policy.status = PolicyStatus.COMPLETED;
            activePolicyId = 0;
            emit PolicyCompleted(policyId);
        }
    }

    function _validateStep(StepInput calldata input, uint256 stepIndex) internal view {
        if (
            input.conditionAsset == address(0) || input.sellToken == address(0) || input.buyToken == address(0)
                || input.sellToken == input.buyToken
        ) revert InvalidStep(stepIndex);
        if (!registry.isSupported(input.conditionAsset)) revert UnsupportedAsset(input.conditionAsset);
        if (!registry.isSupported(input.sellToken)) revert UnsupportedAsset(input.sellToken);
        if (!registry.isSupported(input.buyToken)) revert UnsupportedAsset(input.buyToken);

        AssetRegistry.Asset memory sellAsset = registry.getAsset(input.sellToken);
        AssetRegistry.Asset memory buyAsset = registry.getAsset(input.buyToken);
        bool sellIsSettlement = input.sellToken == settlementToken;
        bool buyIsSettlement = input.buyToken == settlementToken;
        if (!sellIsSettlement && !buyIsSettlement && (!sellAsset.isB20 || !buyAsset.isB20)) {
            revert SettlementPairRequired(input.sellToken, input.buyToken);
        }
        if (sellIsSettlement && !buyAsset.isB20) revert SettlementPairRequired(input.sellToken, input.buyToken);
        if (buyIsSettlement && !sellAsset.isB20) revert SettlementPairRequired(input.sellToken, input.buyToken);

        if (input.amount == 0) revert InvalidStep(stepIndex);
        if (input.amountMode == AmountMode.PERCENT_BALANCE) {
            if (
                input.amount != 2_500 && input.amount != 5_000 && input.amount != 7_500 && input.amount != 10_000
            ) revert InvalidStep(stepIndex);
        }

        if (input.maxDeviationBps >= BPS) revert InvalidStep(stepIndex);
        if (input.expiresAt != 0 && input.expiresAt <= block.timestamp) revert InvalidStep(stepIndex);

        if (input.conditionType == ConditionType.PRICE_ABOVE || input.conditionType == ConditionType.PRICE_BELOW) {
            if (input.threshold == 0) revert InvalidStep(stepIndex);
        } else {
            if (input.deltaBps == 0 || input.deltaBps >= BPS) revert InvalidStep(stepIndex);
        }
    }

    function _captureReference(uint256 policyId, uint8 stepIndex) internal returns (uint256 referencePrice) {
        Step storage step = _steps[policyId][stepIndex];
        (referencePrice,) = registry.priceUsd1e8(step.conditionAsset);
        step.referencePrice = referencePrice;
    }

    function _conditionMet(Step memory step, uint256 currentPrice) internal pure returns (bool) {
        if (step.conditionType == ConditionType.PRICE_ABOVE) return currentPrice >= step.threshold;
        if (step.conditionType == ConditionType.PRICE_BELOW) return currentPrice <= step.threshold;
        if (step.conditionType == ConditionType.UP_BPS_FROM_REFERENCE) {
            return currentPrice * BPS >= step.referencePrice * (BPS + step.deltaBps);
        }
        return currentPrice * BPS <= step.referencePrice * (BPS - step.deltaBps);
    }

    function _resolveSellAmount(Step memory step) internal view returns (uint256) {
        if (step.amountMode == AmountMode.FIXED) return step.amount;
        uint256 balance = IERC20(step.sellToken).balanceOf(address(this));
        return (balance * step.amount) / BPS;
    }

    function _minimumBuyAmount(address sellToken, address buyToken, uint256 sellAmount, uint16 maxDeviationBps)
        internal
        view
        returns (uint256)
    {
        AssetRegistry.Asset memory sellAsset = registry.getAsset(sellToken);
        AssetRegistry.Asset memory buyAsset = registry.getAsset(buyToken);
        (uint256 sellPrice,) = registry.priceUsd1e8(sellToken);
        (uint256 buyPrice,) = registry.priceUsd1e8(buyToken);

        // Keep only one division so a 6-decimal settlement token can quote an
        // 18-decimal B20 asset without losing meaningful precision first.
        uint256 expectedBuy;
        if (buyAsset.tokenDecimals >= sellAsset.tokenDecimals) {
            uint256 scale = 10 ** uint256(buyAsset.tokenDecimals - sellAsset.tokenDecimals);
            expectedBuy = (sellAmount * sellPrice * scale) / buyPrice;
        } else {
            uint256 scale = 10 ** uint256(sellAsset.tokenDecimals - buyAsset.tokenDecimals);
            expectedBuy = (sellAmount * sellPrice) / (buyPrice * scale);
        }

        return (expectedBuy * (BPS - maxDeviationBps)) / BPS;
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = token.call(abi.encodeCall(IERC20.transfer, (to, amount)));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert TokenCallFailed(token, data);
    }

    function _safeTransferFrom(address token, address from, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = token.call(abi.encodeCall(IERC20.transferFrom, (from, to, amount)));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert TokenCallFailed(token, data);
    }

    function _safeApprove(address token, address spender, uint256 amount) internal {
        (bool ok, bytes memory data) = token.call(abi.encodeCall(IERC20.approve, (spender, amount)));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert TokenCallFailed(token, data);
    }
}
