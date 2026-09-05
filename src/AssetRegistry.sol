// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20Metadata} from "./interfaces/IERC20.sol";
import {IAggregatorV3} from "./interfaces/IAggregatorV3.sol";

/// @notice Immutable-price-source registry for Segue-supported assets.
/// @dev Asset token/feed pairs are permanent once registered. The registry owner may
///      only add assets or pause/resume an existing entry; it cannot swap a feed later.
contract AssetRegistry {
    uint256 public constant PRICE_SCALE = 1e8;

    struct Asset {
        address feed;
        uint8 tokenDecimals;
        uint8 feedDecimals;
        uint32 maxStaleness;
        bool isB20;
        bool active;
        bool exists;
    }

    error NotOwner();
    error ZeroAddress();
    error AssetAlreadyRegistered(address token);
    error AssetNotRegistered(address token);
    error InvalidDecimals(uint8 decimals);
    error InvalidStaleness();
    error InactiveAsset(address token);
    error InvalidPrice(address token);
    error StalePrice(address token, uint256 updatedAt);
    error IncompleteRound(address token, uint80 roundId, uint80 answeredInRound);

    event AssetRegistered(
        address indexed token,
        address indexed feed,
        uint8 tokenDecimals,
        uint8 feedDecimals,
        uint32 maxStaleness,
        bool isB20
    );
    event AssetActiveSet(address indexed token, bool active);

    address public immutable owner;
    mapping(address token => Asset asset) private _assets;

    constructor(address owner_) {
        if (owner_ == address(0)) revert ZeroAddress();
        owner = owner_;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    function registerAsset(address token, address feed, uint32 maxStaleness, bool isB20) external onlyOwner {
        if (token == address(0) || feed == address(0)) revert ZeroAddress();
        if (_assets[token].exists) revert AssetAlreadyRegistered(token);
        if (maxStaleness == 0) revert InvalidStaleness();

        uint8 tokenDecimals = IERC20Metadata(token).decimals();
        uint8 feedDecimals = IAggregatorV3(feed).decimals();
        if (tokenDecimals > 18) revert InvalidDecimals(tokenDecimals);
        if (feedDecimals > 18) revert InvalidDecimals(feedDecimals);

        _assets[token] = Asset({
            feed: feed,
            tokenDecimals: tokenDecimals,
            feedDecimals: feedDecimals,
            maxStaleness: maxStaleness,
            isB20: isB20,
            active: true,
            exists: true
        });

        emit AssetRegistered(token, feed, tokenDecimals, feedDecimals, maxStaleness, isB20);
    }

    function setActive(address token, bool active) external onlyOwner {
        Asset storage asset = _assets[token];
        if (!asset.exists) revert AssetNotRegistered(token);
        asset.active = active;
        emit AssetActiveSet(token, active);
    }

    function getAsset(address token) external view returns (Asset memory asset) {
        asset = _assets[token];
        if (!asset.exists) revert AssetNotRegistered(token);
    }

    function isSupported(address token) external view returns (bool) {
        Asset memory asset = _assets[token];
        return asset.exists && asset.active;
    }

    /// @notice Returns the verified USD price normalized to 1e8.
    function priceUsd1e8(address token) external view returns (uint256 price, uint256 updatedAt) {
        Asset memory asset = _assets[token];
        if (!asset.exists) revert AssetNotRegistered(token);
        if (!asset.active) revert InactiveAsset(token);

        (uint80 roundId, int256 answer,, uint256 updatedAt_, uint80 answeredInRound) =
            IAggregatorV3(asset.feed).latestRoundData();

        if (answer <= 0 || updatedAt_ == 0) revert InvalidPrice(token);
        if (answeredInRound < roundId) revert IncompleteRound(token, roundId, answeredInRound);
        if (block.timestamp > updatedAt_ + asset.maxStaleness) revert StalePrice(token, updatedAt_);

        uint256 unsigned = uint256(answer);
        if (asset.feedDecimals == 8) {
            price = unsigned;
        } else if (asset.feedDecimals < 8) {
            price = unsigned * (10 ** uint256(8 - asset.feedDecimals));
        } else {
            price = unsigned / (10 ** uint256(asset.feedDecimals - 8));
        }

        if (price == 0) revert InvalidPrice(token);
        updatedAt = updatedAt_;
    }
}
