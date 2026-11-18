// SPDX-License-Identifier: GPL-3.0-or-later
package config

import (
	"encoding/json"
	"reflect"
	"testing"

	"github.com/metacubex/mihomo/config"
	"github.com/metacubex/mihomo/tunnel"
)

func TestSubscriptionPreservesRoutingAndDNS(t *testing.T) {
	cfg := config.DefaultRawConfig()
	cfg.Mode = tunnel.Global
	cfg.Rule = []string{"DOMAIN,example.com,Provider", "RULE-SET,remote,DIRECT", "MATCH,Provider"}
	cfg.SubRules = map[string][]string{"child": {"MATCH,DIRECT"}}
	cfg.ProxyGroup = []map[string]any{{"name": "Provider", "type": "select", "proxies": []any{"DIRECT"}}}
	cfg.RuleProvider = map[string]map[string]any{"remote": {"type": "http", "url": "https://example.com/rules", "path": "remote.yaml"}}
	cfg.DNS.Enable = true
	cfg.DNS.NameServer = []string{"https://dns.example.com/dns-query"}
	routing := func() []byte {
		b, err := json.Marshal([]any{cfg.Rule, cfg.SubRules, cfg.ProxyGroup, cfg.ProxyProvider, cfg.RuleProvider, cfg.DNS})
		if err != nil {
			t.Fatal(err)
		}
		return b
	}
	before := routing()
	if err := patchSubscriptionRules(cfg, ""); err != nil {
		t.Fatal(err)
	}
	if cfg.Mode != tunnel.Rule {
		t.Fatal("subscription mode must be rule")
	}
	if !reflect.DeepEqual(before, routing()) {
		t.Fatal("subscription routing or DNS was changed")
	}
}

func TestSubscriptionRejectsMissingOrBlankRules(t *testing.T) {
	for _, rules := range [][]string{nil, {}, {" "}, {"MATCH,DIRECT", ""}} {
		cfg := config.DefaultRawConfig()
		cfg.Rule = rules
		if err := patchSubscriptionRules(cfg, ""); err == nil {
			t.Fatalf("accepted incomplete rules: %v", rules)
		}
	}
}

func TestSubscriptionRejectsModeAndRuleOverrides(t *testing.T) {
	for _, slot := range []OverrideSlot{OverrideSlotPersist, OverrideSlotSession} {
		WriteOverride(slot, `{"mode":"global","rules":["MATCH,DIRECT"]}`)
		cfg := config.DefaultRawConfig()
		cfg.Rule = []string{"MATCH,Provider"}
		if err := patchOverride(cfg, ""); err != nil {
			t.Fatal(err)
		}
		if cfg.Mode != tunnel.Rule || !reflect.DeepEqual(cfg.Rule, []string{"MATCH,Provider"}) {
			t.Fatal("override bypassed subscription routing")
		}
		ClearOverride(slot)
		if ReadOverride(slot) != `{"mode":"rule"}` {
			t.Fatal("clear unlocked the policy")
		}
	}
}

func TestSubscriptionClosesAllControllerEndpoints(t *testing.T) {
	cfg := config.DefaultRawConfig()
	cfg.Rule = []string{"MATCH,DIRECT"}
	cfg.ExternalController = "127.0.0.1:9090"
	cfg.ExternalControllerTLS = "127.0.0.1:9091"
	cfg.ExternalControllerUnix = "/tmp/controller.sock"
	cfg.ExternalControllerPipe = "controller"
	if err := patchSubscriptionRules(cfg, ""); err != nil {
		t.Fatal(err)
	}
	if cfg.ExternalController != "" || cfg.ExternalControllerTLS != "" || cfg.ExternalControllerUnix != "" || cfg.ExternalControllerPipe != "" {
		t.Fatal("an external controller can still bypass the rule lock")
	}
}
