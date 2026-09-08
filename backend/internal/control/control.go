// Package control provides the single global "is auto trading allowed right now"
// gate that every order-placing path (Go engine, Python mirror, queue drain)
// must check before acting. It defaults to disabled and persists state to disk
// so a process restart never silently re-enables trading.
package control

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type State struct {
	Enabled   bool      `json:"enabled"`
	Reason    string    `json:"reason"`
	ChangedAt time.Time `json:"changed_at"`
	ChangedBy string    `json:"changed_by"`
}

// Gate is the persisted, authoritative trading-enabled switch.
type Gate struct {
	mu    sync.RWMutex
	state State
	path  string
}

func New(path string) *Gate {
	g := &Gate{path: path}
	g.load()
	return g
}

func (g *Gate) load() {
	data, err := os.ReadFile(g.path)
	if err != nil {
		g.state = State{
			Enabled:   false,
			Reason:    "default: trading not yet enabled",
			ChangedAt: time.Now().UTC(),
			ChangedBy: "system",
		}
		return
	}
	var s State
	if err := json.Unmarshal(data, &s); err != nil {
		g.state = State{
			Enabled:   false,
			Reason:    "default: failed to parse state file",
			ChangedAt: time.Now().UTC(),
			ChangedBy: "system",
		}
		return
	}
	g.state = s
}

func (g *Gate) persist() {
	if dir := filepath.Dir(g.path); dir != "" {
		_ = os.MkdirAll(dir, 0o755)
	}
	data, err := json.MarshalIndent(g.state, "", "  ")
	if err != nil {
		return
	}
	_ = os.WriteFile(g.path, data, 0o644)
}

func (g *Gate) Status() State {
	g.mu.RLock()
	defer g.mu.RUnlock()
	return g.state
}

func (g *Gate) IsEnabled() bool {
	g.mu.RLock()
	defer g.mu.RUnlock()
	return g.state.Enabled
}

func (g *Gate) Enable(by, reason string) State {
	g.mu.Lock()
	defer g.mu.Unlock()
	if reason == "" {
		reason = "enabled"
	}
	g.state = State{Enabled: true, Reason: reason, ChangedAt: time.Now().UTC(), ChangedBy: by}
	g.persist()
	return g.state
}

func (g *Gate) Disable(by, reason string) State {
	g.mu.Lock()
	defer g.mu.Unlock()
	if reason == "" {
		reason = "disabled"
	}
	g.state = State{Enabled: false, Reason: reason, ChangedAt: time.Now().UTC(), ChangedBy: by}
	g.persist()
	return g.state
}
