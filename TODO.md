# MCP Dagu auto-sync — checklist do que fazer

## Objetivo

Garantir que o MCP do Dagu esteja configurado corretamente em todos os pontos relevantes do ambiente local:

- shell zsh
- VS Code
- Claude Code
- Cursor / outros IDEs que usarem MCP por config local
- LaunchAgent de sincronização local

## Estado atual verificado

- O shell local já possui os aliases:
  - `mcp-stop="launchctl unload ~/Library/LaunchAgents/com.user.mcpautosync.plist"`
  - `mcp-start="launchctl load -w ~/Library/LaunchAgents/com.user.mcpautosync.plist"`
  - `mcp-restart="mcp-stop && mcp-start"`
- O LaunchAgent foi criado em:
  - `~/Library/LaunchAgents/com.user.mcpautosync.plist`
- O shell também exporta a chave do MCP a partir do Keychain:
  - `export DAGU_MCP_KEY="$(security find-generic-password -a "$USER" -s dagu-mcp-key -w 2>/dev/null)"`
- O VS Code do workspace foi configurado com o nome:
  - `mcp-dagu-operator`
  - endpoint: `https://jobs.thekonnen.com/mcp`
- O Claude Code foi configurado como servidor `dagu` em `~/.claude.json`.

## Checklist para concluir a replicação

### 1) Validação de shell

Adicionar no `~/.zshrc`:

```bash
# Dagu MCP (jobs.thekonnen.com) — usado pelo Claude Code e VS Code
export DAGU_MCP_KEY="$(security find-generic-password -a "$USER" -s dagu-mcp-key -w 2>/dev/null)"

alias mcp-stop="launchctl unload ~/Library/LaunchAgents/com.user.mcpautosync.plist"
alias mcp-start="launchctl load -w ~/Library/LaunchAgents/com.user.mcpautosync.plist"
alias mcp-restart="mcp-stop && mcp-start"
```

Depois recarregar:

```bash
source ~/.zshrc
```

### 2) Validação do LaunchAgent

O arquivo do agente deve existir em:

```bash
~/Library/LaunchAgents/com.user.mcpautosync.plist
```

E o serviço deve poder ser controlado por:

```bash
mcp-start
mcp-stop
mcp-restart
```

### 3) VS Code

Configurar no arquivo:

```json
{
  "servers": {
    "mcp-dagu-operator": {
      "type": "http",
      "url": "https://jobs.thekonnen.com/mcp",
      "headers": {
        "Authorization": "Bearer ${input:dagu-operator-token}"
      }
    }
  }
}
```

Se quiser preservar o input local em vez de hardcode em arquivo:

```json
{
  "inputs": [
    {
      "id": "dagu-operator-token",
      "type": "promptString",
      "description": "Dagu MCP token (role operator)",
      "password": true
    }
  ],
  "servers": {
    "mcp-dagu-operator": {
      "type": "http",
      "url": "https://jobs.thekonnen.com/mcp",
      "headers": {
        "Authorization": "Bearer ${input:dagu-operator-token}"
      }
    }
  }
}
```

### 4) Claude Code

O config do usuário deve ter um servidor HTTP com endpoint do Dagu:

```json
{
  "mcpServers": {
    "dagu": {
      "type": "http",
      "url": "https://jobs.thekonnen.com/mcp",
      "headers": {
        "Authorization": "Bearer ${DAGU_MCP_KEY}"
      }
    }
  }
}
```

Importante: a chave deve vir do Keychain ou de variável no shell, nunca do repo.

### 5) Cursor / outros IDEs

Para cada IDE que use MCP local, repetir o mesmo padrão:

- endpoint: `https://jobs.thekonnen.com/mcp`
- header Authorization com token do tipo operator
- não guardar token em repositório
- usar variável de ambiente ou input seguro do IDE

### 6) Validação de funcionamento

Testar com:

```bash
curl -s -o /tmp/mcp-init.json -w "HTTP %{http_code}\n" -X POST https://jobs.thekonnen.com/mcp \
  -H "Authorization: Bearer ${DAGU_MCP_KEY}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
```

Resultado esperado:

- resposta HTTP válida
- sem 401/403
- conexão reconhecida pelo MCP

### 7) Regras de segurança

- Nunca comitar a chave real no Git.
- Nunca salvar token em arquivos dentro do repo.
- Usar Keychain do macOS (`security`) ou `input` do editor.
- Se a chave for rotacionada, atualizar em todos os locais relevantes.

## Resumo do que foi verificado

O ambiente já está parcialmente sincronizado em:

- shell local
- LaunchAgent
- VS Code workspace
- Claude Code

Falta padronizar a propagação para os demais IDEs que usam MCP local, usando o mesmo endpoint e o mesmo padrão de autenticação.
