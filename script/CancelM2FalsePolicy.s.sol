// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {StockPolicyVault} from "../src/StockPolicyVault.sol";

interface ICancelM2Vm {
    function envUint(string calldata name) external returns (uint256 value);
    function envAddress(string calldata name) external returns (address value);
    function addr(uint256 privateKey) external returns (address keyAddr);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

/// @notice Cleans up the deliberately false B4 policy after its read-only evidence is saved.
contract CancelM2FalsePolicy {
    ICancelM2Vm internal constant VM =
        ICancelM2Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 internal constant BASE_CHAIN_ID = 8453;

    error WrongChain(uint256 actual);
    error OwnerKeyMismatch(address expected, address actual);
    error VaultOwnerMismatch(address expected, address actual);
    error WrongActivePolicy(uint256 expected, uint256 actual);

    function run() external {
        if (block.chainid != BASE_CHAIN_ID) revert WrongChain(block.chainid);

        uint256 ownerKey = VM.envUint("DEMO_OWNER_PRIVATE_KEY");
        address owner = VM.envAddress("DEMO_OWNER_ADDRESS");
        address actualOwner = VM.addr(ownerKey);
        if (actualOwner != owner) revert OwnerKeyMismatch(owner, actualOwner);

        StockPolicyVault vault = StockPolicyVault(VM.envAddress("DEMO_VAULT_ADDRESS"));
        uint256 policyId = VM.envUint("M2_FALSE_POLICY_ID");
        if (vault.owner() != owner) revert VaultOwnerMismatch(owner, vault.owner());
        if (vault.activePolicyId() != policyId) {
            revert WrongActivePolicy(policyId, vault.activePolicyId());
        }

        VM.startBroadcast(ownerKey);
        vault.cancelPolicy(policyId);
        VM.stopBroadcast();
    }
}
