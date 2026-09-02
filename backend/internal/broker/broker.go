package broker

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/prashant-sriharsh/trade/internal/models"
)

var ErrNotConfigured = fmt.Errorf("broker not configured: set mt5_bridge_url, api_token, and account_id")

// Client executes orders against a broker (MT5 bridge or browser automation).
type Client interface {
	Name() string
	GetAccount(ctx context.Context) (models.Account, error)
	GetQuote(ctx context.Context, symbol string) (models.Quote, error)
	PlaceOrder(ctx context.Context, req models.OrderRequest) (models.Order, error)
	ClosePosition(ctx context.Context, positionID string) (models.ClosedTrade, error)
	ListPositions(ctx context.Context) ([]models.Position, error)
}

// MT5Client talks to an MT5 REST bridge container.
type MT5Client struct {
	baseURL    string
	apiToken   string
	accountID  int
	httpClient *http.Client
}

func NewMT5Client(baseURL, apiToken string, accountID int) *MT5Client {
	return &MT5Client{
		baseURL:   baseURL,
		apiToken:  apiToken,
		accountID: accountID,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

func (c *MT5Client) IsConfigured() bool {
	return c.baseURL != "" && c.apiToken != "" && c.accountID > 0
}

func (c *MT5Client) Name() string { return "mt5-bridge" }

func (c *MT5Client) GetAccount(ctx context.Context) (models.Account, error) {
	if !c.IsConfigured() {
		return models.Account{}, ErrNotConfigured
	}

	url := fmt.Sprintf("%s/api/accounts/%d/data", c.baseURL, c.accountID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return models.Account{}, err
	}
	req.Header.Set("Authorization", "Bearer "+c.apiToken)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return models.Account{}, fmt.Errorf("broker request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return models.Account{}, fmt.Errorf("broker error %d: %s", resp.StatusCode, body)
	}

	var data struct {
		Balance     float64 `json:"balance"`
		Equity      float64 `json:"equity"`
		Margin      float64 `json:"margin"`
		FreeMargin  float64 `json:"free_margin"`
		MarginLevel float64 `json:"margin_level"`
		Leverage    int     `json:"leverage"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return models.Account{}, err
	}

	return models.Account{
		Balance:     data.Balance,
		Equity:      data.Equity,
		Margin:      data.Margin,
		FreeMargin:  data.FreeMargin,
		MarginLevel: data.MarginLevel,
		Leverage:    data.Leverage,
		Currency:    "USD",
	}, nil
}

func (c *MT5Client) GetQuote(ctx context.Context, symbol string) (models.Quote, error) {
	if !c.IsConfigured() {
		return models.Quote{}, ErrNotConfigured
	}

	url := fmt.Sprintf("%s/api/accounts/%d/price/%s", c.baseURL, c.accountID, symbol)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return models.Quote{}, err
	}
	req.Header.Set("Authorization", "Bearer "+c.apiToken)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return models.Quote{}, fmt.Errorf("broker quote: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return models.Quote{}, fmt.Errorf("broker quote error: status %d", resp.StatusCode)
	}

	var q struct {
		Bid float64 `json:"bid"`
		Ask float64 `json:"ask"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&q); err != nil {
		return models.Quote{}, err
	}

	return models.Quote{
		Symbol: symbol,
		Bid:    q.Bid,
		Ask:    q.Ask,
		Spread: q.Ask - q.Bid,
		Time:   time.Now().UTC(),
	}, nil
}

func (c *MT5Client) PlaceOrder(ctx context.Context, req models.OrderRequest) (models.Order, error) {
	if !c.IsConfigured() {
		return models.Order{}, ErrNotConfigured
	}
	// Order placement schema depends on bridge vendor — implement when bridge is running.
	return models.Order{}, fmt.Errorf("live order placement not yet implemented — awaiting MT5 bridge setup")
}

func (c *MT5Client) ClosePosition(ctx context.Context, positionID string) (models.ClosedTrade, error) {
	if !c.IsConfigured() {
		return models.ClosedTrade{}, ErrNotConfigured
	}
	return models.ClosedTrade{}, fmt.Errorf("live position close not yet implemented")
}

func (c *MT5Client) ListPositions(ctx context.Context) ([]models.Position, error) {
	if !c.IsConfigured() {
		return nil, ErrNotConfigured
	}

	url := fmt.Sprintf("%s/api/accounts/%d/positions", c.baseURL, c.accountID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.apiToken)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("broker positions error: status %d", resp.StatusCode)
	}

	var positions []models.Position
	if err := json.NewDecoder(resp.Body).Decode(&positions); err != nil {
		return nil, err
	}
	return positions, nil
}

// BrowserAutomation talks to the Python browser bridge (strategy/browser_bridge.py)
// or relays state synced from Cursor browser MCP.
type BrowserAutomation struct {
	enabled    bool
	baseURL    string
	bridgeURL  string
	httpClient *http.Client
}

func NewBrowserAutomation(baseURL string) *BrowserAutomation {
	bridgeURL := os.Getenv("BROWSER_BRIDGE_URL")
	if bridgeURL == "" {
		bridgeURL = "http://127.0.0.1:8090"
	}
	return &BrowserAutomation{
		enabled:   false,
		baseURL:   baseURL,
		bridgeURL: bridgeURL,
		httpClient: &http.Client{Timeout: 15 * time.Second},
	}
}

func (b *BrowserAutomation) Name() string { return "browser-automation" }

func (b *BrowserAutomation) Enable() {
	b.enabled = true
}

func (b *BrowserAutomation) EnableBridge(ctx context.Context) error {
	b.enabled = true
	return b.bridgePost(ctx, "/api/v1/browser/enable", map[string]string{}, nil)
}

func (b *BrowserAutomation) IsEnabled() bool {
	return b.enabled
}

func (b *BrowserAutomation) Status() string {
	if !b.enabled {
		return "disabled — log in to Exness web terminal, start browser_bridge.py, then POST /api/v1/broker/browser/enable"
	}
	return fmt.Sprintf("ready — bridge %s, exness %s", b.bridgeURL, b.baseURL)
}

func (b *BrowserAutomation) bridgeGet(ctx context.Context, path string, dest any) error {
	if !b.enabled {
		return fmt.Errorf("browser automation not enabled")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, b.bridgeURL+path, nil)
	if err != nil {
		return err
	}
	resp, err := b.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("browser bridge: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("browser bridge %d: %s", resp.StatusCode, body)
	}
	return json.NewDecoder(resp.Body).Decode(dest)
}

func (b *BrowserAutomation) bridgePost(ctx context.Context, path string, payload any, dest any) error {
	if !b.enabled {
		return fmt.Errorf("browser automation not enabled")
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, b.bridgeURL+path, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := b.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("browser bridge: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("browser bridge %d: %s", resp.StatusCode, body)
	}
	if dest != nil {
		return json.NewDecoder(resp.Body).Decode(dest)
	}
	return nil
}

func (b *BrowserAutomation) SyncQuote(ctx context.Context, quote models.Quote, balance, equity float64) error {
	return b.bridgePost(ctx, "/api/v1/sync", map[string]any{
		"symbol":   quote.Symbol,
		"bid":      quote.Bid,
		"ask":      quote.Ask,
		"balance":  balance,
		"equity":   equity,
	}, nil)
}

func (b *BrowserAutomation) GetAccount(ctx context.Context) (models.Account, error) {
	var acc models.Account
	if err := b.bridgeGet(ctx, "/api/v1/account", &acc); err != nil {
		return models.Account{}, err
	}
	return acc, nil
}

func (b *BrowserAutomation) GetQuote(ctx context.Context, symbol string) (models.Quote, error) {
	var q models.Quote
	if err := b.bridgeGet(ctx, "/api/v1/quote/"+symbol, &q); err != nil {
		return models.Quote{}, err
	}
	return q, nil
}

func (b *BrowserAutomation) PlaceOrder(ctx context.Context, req models.OrderRequest) (models.Order, error) {
	var result map[string]any
	err := b.bridgePost(ctx, "/api/v1/orders", map[string]any{
		"side":        req.Side,
		"volume":      req.Volume,
		"stop_loss":   req.StopLoss,
		"take_profit": req.TakeProfit,
	}, &result)
	if err != nil {
		return models.Order{}, err
	}
	return models.Order{
		Status:  models.OrderStatusFilled,
		Message: fmt.Sprintf("browser: %v", result["status"]),
		Request: req,
	}, nil
}

func (b *BrowserAutomation) ClosePosition(ctx context.Context, positionID string) (models.ClosedTrade, error) {
	return models.ClosedTrade{}, fmt.Errorf("browser close not yet implemented for position %s", positionID)
}

func (b *BrowserAutomation) ListPositions(ctx context.Context) ([]models.Position, error) {
	var positions []models.Position
	if err := b.bridgeGet(ctx, "/api/v1/positions", &positions); err != nil {
		return nil, err
	}
	return positions, nil
}
