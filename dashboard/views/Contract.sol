// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title ShipmentEscrow (centralized, seller-activates-from-Pending)
/// @notice Contract records shipment state and emits events; backend handles actual money off-chain.
contract ShipmentEscrow {
    // IMMUTABLE SHIPMENT DETAILS
    address public immutable buyer;
    address public immutable seller;
    uint256 public immutable price;

    int256 public immutable minTemp;
    int256 public immutable maxTemp;
    uint256 public immutable temperatureTime;   // minutes required for breach

    string public vaccineName;
    uint256 public vaccineQuantity;

    // STATE MACHINE
    enum State { Pending, Active, Completed, Refunded }
    State public state;

    // EVENTS
    event ShipmentActivated(address seller);
    event PaymentReleaseRequested(address to, uint256 amount);
    event PaymentRefundRequested(address to, uint256 amount);
    event ShipmentCompleted(address caller);
    event ShipmentRefunded(address caller);

    // MODIFIERS
    modifier onlyBuyer() {
        require(msg.sender == buyer, "Only buyer");
        _;
    }

    modifier onlySeller() {
        require(msg.sender == seller, "Only seller");
        _;
    }

    modifier inState(State expected) {
        require(state == expected, "Invalid state");
        _;
    }

    // CONSTRUCTOR (8 args)
    constructor(
        address _buyer,
        address _seller,
        uint256 _price,
        int256 _minTemp,
        int256 _maxTemp,
        uint256 _temperatureTime,
        string memory _vaccineName,
        uint256 _vaccineQuantity
    ) {
        require(_buyer != address(0), "Invalid buyer");
        require(_seller != address(0), "Invalid seller");
        require(_price > 0, "Price > 0");
        require(_temperatureTime > 0, "temperature_time > 0");

        buyer = _buyer;
        seller = _seller;
        price = _price;

        minTemp = _minTemp;
        maxTemp = _maxTemp;
        temperatureTime = _temperatureTime;

        vaccineName = _vaccineName;
        vaccineQuantity = _vaccineQuantity;

        state = State.Pending;
    }

    // SELLER ACTIVATES SHIPMENT (from Pending -> Active)
    function activateShipment()
        external
        onlySeller
        inState(State.Pending)
    {
        state = State.Active;
        emit ShipmentActivated(msg.sender);
    }

    // COMPLETE: admin/back-end or buyer can call to record completion — backend does off-chain payout
    function completeShipment()
        external
        inState(State.Active)
    {
        require(msg.sender == buyer || msg.sender == tx.origin, "Only buyer or admin");
        emit PaymentReleaseRequested(seller, price);
        state = State.Completed;
        emit ShipmentCompleted(msg.sender);
    }

    // REFUND: only admin/back-end should call (but use tx.origin or server signer)
    function refundShipment()
        external
        inState(State.Active)
    {
        // In centralized flow, restrict to tx.origin (or implement different admin check)
        require(msg.sender == tx.origin, "Only admin/backend");
        emit PaymentRefundRequested(buyer, price);
        state = State.Refunded;
        emit ShipmentRefunded(msg.sender);
    }

    // read-only helpers
    function getState() external view returns (State) {
        return state;
    }

    // contract does not accept ETH in centralized mode
    receive() external payable {
        revert("Contract does not accept ETH");
    }
    fallback() external payable {
        revert("Contract does not accept ETH");
    }
}
