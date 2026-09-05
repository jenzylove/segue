// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {StockPolicyVault} from "./StockPolicyVault.sol";

/// @notice Permissionless one-vault-per-wallet factory.
/// @dev The factory has no admin withdrawal or policy authority over deployed vaults.
contract StockPolicyVaultFactory {
    error ZeroAddress();
    error VaultAlreadyExists(address owner, address vault);

    event VaultCreated(
        address indexed owner,
        address indexed vault,
        address indexed executor,
        uint256 maxDeployedUSDC
    );

    address public immutable registry;
    address public immutable settlementToken;
    address public immutable allowanceHolder;

    mapping(address owner => address vault) public vaultOf;
    mapping(address vault => bool) public isVault;

    constructor(address registry_, address settlementToken_, address allowanceHolder_) {
        if (registry_ == address(0) || settlementToken_ == address(0) || allowanceHolder_ == address(0)) {
            revert ZeroAddress();
        }
        registry = registry_;
        settlementToken = settlementToken_;
        allowanceHolder = allowanceHolder_;
    }

    function createVault(address executor, uint256 maxDeployedUSDC) external returns (address vault) {
        if (executor == address(0)) revert ZeroAddress();
        address existing = vaultOf[msg.sender];
        if (existing != address(0)) revert VaultAlreadyExists(msg.sender, existing);

        vault = address(
            new StockPolicyVault(
                msg.sender,
                executor,
                registry,
                settlementToken,
                allowanceHolder,
                maxDeployedUSDC
            )
        );
        vaultOf[msg.sender] = vault;
        isVault[vault] = true;

        emit VaultCreated(msg.sender, vault, executor, maxDeployedUSDC);
    }
}
