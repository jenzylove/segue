// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IM2AttributionVm {
    function envString(string calldata name) external returns (string memory);
}

/// @dev Script-only ERC-8021 schema 0; no changes to deployed vault contracts.
/// Encoding matches ox/erc8021 Attribution.toDataSuffix({codes: [code]}).
library M2Attribution {
    error InvalidBuilderCode();
    error TargetHasNoCode(address target);

    function suffix(string memory code) internal pure returns (bytes memory) {
        bytes memory value = bytes(code);
        if (value.length == 0 || value.length > 255) revert InvalidBuilderCode();
        for (uint256 i; i < value.length; ++i) {
            // One printable ASCII code; commas would encode multiple entities.
            if (uint8(value[i]) < 33 || uint8(value[i]) > 126 || value[i] == ",") {
                revert InvalidBuilderCode();
            }
        }
        return abi.encodePacked(value, uint8(value.length), hex"00", hex"80218021802180218021802180218021");
    }

    function configuredSuffix() internal returns (bytes memory) {
        IM2AttributionVm vm = IM2AttributionVm(address(uint160(uint256(keccak256("hevm cheat code")))));
        return suffix(vm.envString("BASE_BUILDER_CODE"));
    }

    function callWithSuffix(address target, bytes memory data, bytes memory attribution)
        internal
        returns (bytes memory result)
    {
        if (target.code.length == 0) revert TargetHasNoCode(target);
        bool ok;
        (ok, result) = target.call(bytes.concat(data, attribution));
        if (!ok) {
            assembly ("memory-safe") { revert(add(result, 32), mload(result)) }
        }
    }
}
