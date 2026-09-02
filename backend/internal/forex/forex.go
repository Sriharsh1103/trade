package forex

import "strings"

const ContractSize = 100_000.0
const GoldContractSize = 100.0 // oz per standard lot on MT5/Exness

func IsGold(symbol string) bool {
	s := strings.ToUpper(symbol)
	return strings.Contains(s, "XAU") || strings.Contains(s, "GOLD")
}

func ContractSizeFor(symbol string) float64 {
	if IsGold(symbol) {
		return GoldContractSize
	}
	return ContractSize
}

func PipSize(symbol string) float64 {
	s := strings.ToUpper(symbol)
	if IsGold(s) {
		return 0.01 // $0.01 price increment
	}
	if strings.Contains(s, "JPY") {
		return 0.01
	}
	return 0.0001
}

func Notional(symbol string, volume, price float64) float64 {
	return volume * ContractSizeFor(symbol) * price
}

func Margin(symbol string, volume, price float64, leverage int) float64 {
	if leverage <= 0 {
		leverage = 100
	}
	return Notional(symbol, volume, price) / float64(leverage)
}

func UnrealizedPL(symbol, side string, entry, current, volume float64) float64 {
	diff := current - entry
	if side == "sell" {
		diff = entry - current
	}
	return diff * volume * ContractSizeFor(symbol)
}

// Legacy helper for forex pairs (non-gold).
func UnrealizedPLPair(side string, entry, current, volume float64) float64 {
	return UnrealizedPL("", side, entry, current, volume)
}

func PriceForProfit(symbol, side string, entry, volume, targetProfit float64) float64 {
	if volume <= 0 {
		return entry
	}
	delta := targetProfit / (volume * ContractSizeFor(symbol))
	if side == "buy" {
		return entry + delta
	}
	return entry - delta
}

func PriceForLoss(symbol, side string, entry, volume, maxLoss float64) float64 {
	if volume <= 0 {
		return entry
	}
	delta := maxLoss / (volume * ContractSizeFor(symbol))
	if side == "buy" {
		return entry - delta
	}
	return entry + delta
}
