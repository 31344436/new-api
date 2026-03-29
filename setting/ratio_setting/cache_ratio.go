package ratio_setting

import (
	"github.com/QuantumNous/new-api/types"
)

var defaultCacheRatio = map[string]float64{
	"gpt-5.4":                            0.1,
	"gpt-5.4-mini":                       0.1,
	"gpt-5.3-codex":                      0.1,
	"claude-sonnet-4-6":                  0.1,
	"claude-opus-4-6":                    0.1,
	"claude-opus-4-6-max":                0.1,
	"claude-opus-4-6-high":               0.1,
	"claude-opus-4-6-medium":             0.1,
	"claude-opus-4-6-low":                0.1,
	"gemini-3.1-pro-preview":             0.1,
	"gemini-3.1-pro-preview-customtools": 0.1,
}

var defaultCreateCacheRatio = map[string]float64{
	"claude-sonnet-4-6":      1.25,
	"claude-opus-4-6":        1.25,
	"claude-opus-4-6-max":    1.25,
	"claude-opus-4-6-high":   1.25,
	"claude-opus-4-6-medium": 1.25,
	"claude-opus-4-6-low":    1.25,
}

//var defaultCreateCacheRatio = map[string]float64{}

var cacheRatioMap = types.NewRWMap[string, float64]()
var createCacheRatioMap = types.NewRWMap[string, float64]()

// GetCacheRatioMap returns a copy of the cache ratio map
func GetCacheRatioMap() map[string]float64 {
	return cacheRatioMap.ReadAll()
}

// CacheRatio2JSONString converts the cache ratio map to a JSON string
func CacheRatio2JSONString() string {
	return cacheRatioMap.MarshalJSONString()
}

// CreateCacheRatio2JSONString converts the create cache ratio map to a JSON string
func CreateCacheRatio2JSONString() string {
	return createCacheRatioMap.MarshalJSONString()
}

// UpdateCacheRatioByJSONString updates the cache ratio map from a JSON string
func UpdateCacheRatioByJSONString(jsonStr string) error {
	return types.LoadFromJsonStringWithCallback(cacheRatioMap, jsonStr, InvalidateExposedDataCache)
}

// UpdateCreateCacheRatioByJSONString updates the create cache ratio map from a JSON string
func UpdateCreateCacheRatioByJSONString(jsonStr string) error {
	return types.LoadFromJsonStringWithCallback(createCacheRatioMap, jsonStr, InvalidateExposedDataCache)
}

// GetCacheRatio returns the cache ratio for a model
func GetCacheRatio(name string) (float64, bool) {
	ratio, ok := cacheRatioMap.Get(name)
	if !ok {
		return 1, false // Default to 1 if not found
	}
	return ratio, true
}

func GetCreateCacheRatio(name string) (float64, bool) {
	ratio, ok := createCacheRatioMap.Get(name)
	if !ok {
		return 1.25, false // Default to 1.25 if not found
	}
	return ratio, true
}

func GetCacheRatioCopy() map[string]float64 {
	return cacheRatioMap.ReadAll()
}

func GetCreateCacheRatioCopy() map[string]float64 {
	return createCacheRatioMap.ReadAll()
}
