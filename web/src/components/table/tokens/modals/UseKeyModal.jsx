/*
Copyright (C) 2025 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/

import React, { useState, useEffect } from 'react';
import { Modal, Tabs, TabPane, Button, Spin } from '@douyinfe/semi-ui';
import { IconCopy } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { copy, showSuccess, showError } from '../../../../helpers';
import { fetchTokenKey, getServerAddress } from '../../../../helpers/token';

function CodeBlock({ code, filename }) {
  const { t } = useTranslation();

  const handleCopy = async () => {
    if (await copy(code)) {
      showSuccess(t('已复制到剪贴板！'));
    } else {
      showError(t('复制失败'));
    }
  };

  return (
    <div style={{ marginBottom: 12 }}>
      {filename && (
        <div
          style={{
            fontSize: 12,
            color: 'var(--semi-color-text-2)',
            marginBottom: 4,
          }}
        >
          {filename}
        </div>
      )}
      <div
        style={{
          position: 'relative',
          background: '#1e1e2e',
          borderRadius: 8,
          overflow: 'hidden',
        }}
      >
        <Button
          icon={<IconCopy />}
          size='small'
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            color: '#aaa',
            background: 'rgba(255,255,255,0.12)',
            border: 'none',
            zIndex: 1,
          }}
          onClick={handleCopy}
        >
          {t('复制')}
        </Button>
        <pre
          style={{
            margin: 0,
            padding: '12px 16px',
            paddingRight: 90,
            fontFamily: 'monospace',
            fontSize: 13,
            color: '#cdd6f4',
            overflowX: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            lineHeight: 1.6,
          }}
        >
          {code}
        </pre>
      </div>
    </div>
  );
}

export default function UseKeyModal({ visible, onCancel, record }) {
  const { t } = useTranslation();
  const [apiKey, setApiKey] = useState('sk-...');
  const [loading, setLoading] = useState(false);

  const serverAddress = getServerAddress();
  const baseUrl = `${serverAddress}/v1`;

  useEffect(() => {
    if (!visible || !record?.id) return;
    setApiKey('sk-...');
    setLoading(true);
    fetchTokenKey(record.id)
      .then((key) => setApiKey(`sk-${key}`))
      .catch(() => setApiKey('sk-...'))
      .finally(() => setLoading(false));
  }, [visible, record?.id]);

  const macLinuxTerminal = [
    `export ANTHROPIC_BASE_URL="${baseUrl}"`,
    `export ANTHROPIC_AUTH_TOKEN="${apiKey}"`,
    `export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`,
  ].join('\n');

  const vscodeSettings = JSON.stringify(
    {
      env: {
        ANTHROPIC_BASE_URL: baseUrl,
        ANTHROPIC_AUTH_TOKEN: apiKey,
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1',
      },
    },
    null,
    2,
  );

  const windowsCmd = [
    `set ANTHROPIC_BASE_URL=${baseUrl}`,
    `set ANTHROPIC_AUTH_TOKEN=${apiKey}`,
    `set CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`,
  ].join('\n');

  const powershell = [
    `$env:ANTHROPIC_BASE_URL="${baseUrl}"`,
    `$env:ANTHROPIC_AUTH_TOKEN="${apiKey}"`,
    `$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`,
  ].join('\n');

  return (
    <Modal
      title={t('使用 API 密钥')}
      visible={visible}
      onCancel={onCancel}
      footer={<Button onClick={onCancel}>{t('关闭')}</Button>}
      width={640}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin />
        </div>
      ) : (
        <Tabs type='line'>
          <TabPane tab='Claude Code' itemKey='claude-code'>
            <p
              style={{
                color: 'var(--semi-color-text-2)',
                marginBottom: 12,
                fontSize: 13,
              }}
            >
              {t('将以下环境变量添加到您的终端配置文件或直接在终端中运行。')}
            </p>
            <Tabs type='button'>
              <TabPane tab='macOS / Linux' itemKey='mac'>
                <div style={{ marginTop: 12 }}>
                  <CodeBlock filename='Terminal' code={macLinuxTerminal} />
                  <CodeBlock
                    filename='~/.claude/settings.json'
                    code={vscodeSettings}
                  />
                </div>
              </TabPane>
              <TabPane tab='Windows CMD' itemKey='cmd'>
                <div style={{ marginTop: 12 }}>
                  <CodeBlock code={windowsCmd} />
                  <CodeBlock
                    filename='~/.claude/settings.json'
                    code={vscodeSettings}
                  />
                </div>
              </TabPane>
              <TabPane tab='PowerShell' itemKey='ps'>
                <div style={{ marginTop: 12 }}>
                  <CodeBlock code={powershell} />
                  <CodeBlock
                    filename='~/.claude/settings.json'
                    code={vscodeSettings}
                  />
                </div>
              </TabPane>
            </Tabs>
          </TabPane>
        </Tabs>
      )}
    </Modal>
  );
}
