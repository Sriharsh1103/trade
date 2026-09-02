package models

import "time"

type Side string

const (
	SideBuy  Side = "buy"
	SideSell Side = "sell"
)

type OrderType string

const (
	OrderTypeMarket OrderType = "market"
	OrderTypeLimit  OrderType = "limit"
	OrderTypeStop   OrderType = "stop"
)

type OrderStatus string

const (
	OrderStatusPending   OrderStatus = "pending"
	OrderStatusFilled    OrderStatus = "filled"
	OrderStatusRejected  OrderStatus = "rejected"
	OrderStatusCancelled OrderStatus = "cancelled"
)

type SignalAction string

const (
	SignalBuy  SignalAction = "buy"
	SignalSell SignalAction = "sell"
	SignalHold SignalAction = "hold"
)

type Quote struct {
	Symbol string  `json:"symbol"`
	Bid    float64 `json:"bid"`
	Ask    float64 `json:"ask"`
	Spread float64 `json:"spread"`
	Time   time.Time `json:"time"`
}

type Account struct {
	Balance     float64 `json:"balance"`
	Equity      float64 `json:"equity"`
	Margin      float64 `json:"margin"`
	FreeMargin  float64 `json:"free_margin"`
	MarginLevel float64 `json:"margin_level"`
	Leverage    int     `json:"leverage"`
	Currency    string  `json:"currency"`
}

type Signal struct {
	Symbol     string       `json:"symbol"`
	Action     SignalAction `json:"action"`
	Confidence float64      `json:"confidence"`
	Source     string       `json:"source,omitempty"`
}

type OrderRequest struct {
	Symbol   string    `json:"symbol"`
	Side     Side      `json:"side"`
	Type     OrderType `json:"type"`
	Volume   float64   `json:"volume"`
	Price    float64   `json:"price,omitempty"`
	StopLoss float64   `json:"stop_loss"`
	TakeProfit float64 `json:"take_profit"`
}

type Order struct {
	ID         string      `json:"id"`
	Request    OrderRequest `json:"request"`
	Status     OrderStatus `json:"status"`
	FillPrice  float64     `json:"fill_price,omitempty"`
	Message    string      `json:"message,omitempty"`
	CreatedAt  time.Time   `json:"created_at"`
	FilledAt   *time.Time  `json:"filled_at,omitempty"`
}

type Position struct {
	ID           string    `json:"id"`
	OrderID      string    `json:"order_id"`
	Symbol       string    `json:"symbol"`
	Side         Side      `json:"side"`
	Volume       float64   `json:"volume"`
	EntryPrice   float64   `json:"entry_price"`
	CurrentPrice float64   `json:"current_price"`
	StopLoss     float64   `json:"stop_loss"`
	TakeProfit   float64   `json:"take_profit"`
	Margin       float64   `json:"margin"`
	UnrealizedPL float64   `json:"unrealized_pl"`
	OpenedAt     time.Time `json:"opened_at"`
}

type CloseReason string

const (
	CloseReasonManual     CloseReason = "manual"
	CloseReasonTakeProfit CloseReason = "take_profit"
	CloseReasonStopLoss   CloseReason = "stop_loss"
	CloseReasonAutoExit   CloseReason = "auto_exit"
	CloseReasonEmergency  CloseReason = "emergency"
)

type ClosedTrade struct {
	Position   Position    `json:"position"`
	ExitPrice  float64     `json:"exit_price"`
	RealizedPL float64     `json:"realized_pl"`
	Reason     CloseReason `json:"reason"`
	ClosedAt   time.Time   `json:"closed_at"`
}

type RiskStatus struct {
	DailyStartBalance float64 `json:"daily_start_balance"`
	DailyPL           float64 `json:"daily_pl"`
	DailyLossLimit    float64 `json:"daily_loss_limit"`
	OpenPositions     int     `json:"open_positions"`
	MaxOpenPositions  int     `json:"max_open_positions"`
	TradingAllowed    bool    `json:"trading_allowed"`
	Reason            string  `json:"reason,omitempty"`
}
