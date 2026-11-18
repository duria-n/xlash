// SPDX-License-Identifier: GPL-3.0-or-later
package config

import (
	"errors"
	"fmt"
	"strings"

	"github.com/metacubex/mihomo/config"
	"github.com/metacubex/mihomo/tunnel"
)

// patchSubscriptionRules deliberately leaves the rule order, groups, sub-rules
// and provider definitions untouched. Android's existing transport adaptations
// still run afterwards. This is a dedicated subscription-rules build.
func patchSubscriptionRules(cfg *config.RawConfig, _ string) error {
	if len(cfg.Rule) == 0 {
		return errors.New("订阅没有提供 rules 分流规则；请使用订阅方的 Clash/Mihomo 完整配置，不能只导入节点")
	}
	for i, rule := range cfg.Rule {
		if strings.TrimSpace(rule) == "" {
			return fmt.Errorf("订阅第 %d 条规则为空，配置未应用", i+1)
		}
	}
	cfg.Mode = tunnel.Rule
	// Also close non-TCP controller endpoints: an external mode change would
	// contradict the app's promise to keep subscription routing active.
	cfg.ExternalController = ""
	cfg.ExternalControllerTLS = ""
	cfg.ExternalControllerUnix = ""
	cfg.ExternalControllerPipe = ""
	return nil
}

// Parsing provider definitions alone does not validate their payloads. Run this
// before promoting the processing directory to the imported profile. The caller
// must close all providers even when one of them fails.
func validateSubscriptionProviders(cfg *config.Config) error {
	for name, p := range cfg.RuleProviders {
		if err := p.Initial(); err != nil {
			// Underlying HTTP errors may contain credential-bearing subscription URLs.
			return fmt.Errorf("规则集 %q 初始化失败；请检查网络或规则集内容，配置未应用", name)
		}
	}
	return nil
}
