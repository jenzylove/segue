// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {StockPolicyVault} from "../src/StockPolicyVault.sol";

interface IExecuteVm {
    function envUint(string calldata name) external returns (uint256 value);
    function envAddress(string calldata name) external returns (address value);
    function envBytes(string calldata name) external returns (bytes memory value);
    function addr(uint256 privateKey) external returns (address keyAddr);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Broadcast one already-validated 1inch route through the bounded Segue vault.
/// @dev This script never calls 1inch directly from the executor EOA. The vault remains
///      the caller, grants the exact sell allowance, checks the oracle condition and
///      verifies exact sell/minimum buy postconditions before advancing state.
contract ExecuteM2Quote {
    IExecuteVm internal constant VM = IExecuteVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 internal constant BASE_CHAIN_ID = 8453;

    error WrongChain(uint256 actual);
    error ExecutorKeyMismatch(address expected, address actual);
    error VaultExecutorMismatch(address expected, address actual);
    error ExecutionTargetMismatch(address expected, address actual);
    error MissingExecutionTargetCode(address target);
    error InvalidPolicyId();
    error EmptyRouteCalldata();
    error StepNotExecutable(uint8 reason);

    function run() external {
        if (block.chainid != BASE_CHAIN_ID) revert WrongChain(block.chainid);

        uint256 privateKey = VM.envUint("EXECUTOR_PRIVATE_KEY");
        address expectedExecutor = VM.envAddress("EXECUTOR_ADDRESS");
        address actualExecutor = VM.addr(privateKey);
        if (actualExecutor != expectedExecutor) revert ExecutorKeyMismatch(expectedExecutor, actualExecutor);

        StockPolicyVault vault = StockPolicyVault(VM.envAddress("DEMO_VAULT_ADDRESS"));
        address executionTarget = VM.envAddress("EXECUTION_TARGET_ADDRESS");
        uint256 policyId = VM.envUint("M2_POLICY_ID");
        bytes memory routeCalldata = VM.envBytes("M2_ROUTE_CALLDATA");

        if (policyId == 0) revert InvalidPolicyId();
        if (routeCalldata.length < 4) revert EmptyRouteCalldata();
        if (executionTarget.code.length == 0) revert MissingExecutionTargetCode(executionTarget);
        if (vault.executor() != expectedExecutor) revert VaultExecutorMismatch(expectedExecutor, vault.executor());
        if (vault.allowanceHolder() != executionTarget) {
            revert ExecutionTargetMismatch(executionTarget, vault.allowanceHolder());
        }

        (bool executable, StockPolicyVault.PreviewReason reason,,,) = vault.previewExecution(policyId);
        if (!executable) revert StepNotExecutable(uint8(reason));

        VM.startBroadcast(privateKey);
        vault.executeStep(policyId, routeCalldata);
        VM.stopBroadcast();
    }
}
