// SPDX-License-Identifier: GPL-3.0-or-later
package config

type OverrideSlot int

const (
	OverrideSlotPersist OverrideSlot = iota
	OverrideSlotSession
)

// Both the UI and the core see the same effective mode. Old override.json files
// are intentionally ignored; neither a session override nor a restored setting
// may replace provider rules, DNS, groups, or mode in this build.
func ReadOverride(_ OverrideSlot) string {
	return `{"mode":"rule"}`
}

func WriteOverride(_ OverrideSlot, _ string) {}

func ClearOverride(_ OverrideSlot) {}
