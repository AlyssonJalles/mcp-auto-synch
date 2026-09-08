# MCP Sync (Português)

Um aplicativo leve, que fica sempre ativo na **barra de menu / bandeja do
sistema**, e mantém a configuração dos seus **servidores MCP (Model Context
Protocol)** sincronizada entre todas as ferramentas de IA instaladas na sua
máquina — Codex, Claude Code, Cursor, Gemini CLI, GitHub Copilot CLI, VS
Code, OpenCode, Windsurf, Antigravity, Zed, Continue, Roo Code, Claude
Desktop, Cline, Kilo Code, Zoo Code, Amp, Kiro, Amazon Q, Goose, Warp, Trae,
LM Studio e Grok.

Funciona em **macOS (Apple Silicon e Intel), Ubuntu/Linux e Windows**.

> O restante da documentação e todo o código-fonte estão em inglês
> (`README.md`, comentários, etc.) — este arquivo é só o guia rápido de
> instalação e uso em português.

## Por que existe

Cada uma dessas ferramentas guarda sua própria lista de servidores MCP em
um arquivo de configuração próprio, com um formato próprio. Se você
adiciona um servidor MCP em uma ferramenta, ele simplesmente não existe nas
outras. O MCP Sync observa todos esses arquivos, junta os servidores
encontrados e escreve o conjunto combinado de volta em cada ferramenta —
no formato nativo dela — então você só precisa cadastrar um servidor uma
única vez.

## Como funciona na prática

- Um pequeno ícone de sincronização fica na barra de menu (macOS) / bandeja
  do sistema (Windows, Linux) o tempo todo, e o app inicia automaticamente
  no login.
- Ao clicar no ícone, você vê cada ferramenta detectada, a quantidade de
  servidores MCP dela, e uma bolinha de status:
  - 🟢 verde — instalada, habilitada e totalmente sincronizada
  - ⚪ cinza — instalada e habilitada, mas uma sincronização está pendente
    (deve se resolver na próxima passagem, normalmente em poucos segundos)
  - ⬛ preta — instalada, mas **você desligou a sincronização** dessa
    ferramenta
  - Ferramentas não instaladas na máquina aparecem separadas, em uma linha
    informativa, e são ignoradas.
- Clique no nome de qualquer ferramenta no menu para desligar a
  sincronização dela — o MCP Sync para de ler e escrever no arquivo de
  configuração dessa ferramenta até você ligar de novo. Nada mais na
  ferramenta é alterado.
- "Sync Now" força uma sincronização imediata. "Start at Login" liga/desliga
  o item de inicialização automática do sistema operacional.

## Como a sincronização funciona

1. Ao iniciar, sempre que um arquivo monitorado muda (detecção instantânea
   via eventos do sistema de arquivos) ou a cada 60 segundos como
   segurança extra, o MCP Sync lê a lista de servidores MCP de cada
   ferramenta **habilitada** e **detectada**.
2. Ele combina todos os servidores em um único conjunto. Se o mesmo nome de
   servidor existir em mais de uma ferramenta com configurações
   diferentes, **o arquivo editado mais recentemente vence** para aquele
   servidor.
3. Ele escreve o conjunto combinado de volta no arquivo de configuração de
   cada ferramenta habilitada/detectada, traduzido para o formato nativo
   dela — sem tocar em nenhuma outra configuração daquele arquivo (o
   `inputs` do VS Code, outras chaves do Claude, etc. são preservados como
   estão).
4. Um arquivo só é reescrito se o conteúdo realmente precisar mudar, então
   isso nunca dispara notificações falsas de "arquivo modificado" em outro
   lugar nem sobrecarrega o disco com escritas desnecessárias.

Nada é enviado pela rede — o app só lê/escreve arquivos locais que já
existem na sua máquina.

## Instalação

### macOS
```bash
./installers/install_macos.sh
```

### Ubuntu / Linux
```bash
./installers/install_linux.sh
```
Requer bandeja do sistema / AppIndicator (habilitado por padrão no GNOME do
Ubuntu). Se o ícone não aparecer, veja a mensagem que o instalador imprime
sobre o pacote `gir1.2-ayatana-appindicator3-0.1`.

### Windows
No PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File installers\install_windows.ps1
```

Cada instalador cria um ambiente virtual Python isolado em
`~/.mcp-sync/venv` (mantendo o app "leve" e sem misturar com o Python do
sistema), registra o app para iniciar no login, e já inicia ele na hora.

**Para desinstalar**: rode o script `installers/uninstall_*` correspondente
ao seu sistema operacional (`uninstall_macos.sh`, `uninstall_linux.sh` ou
`uninstall_windows.ps1`).

## Onde ficam as configurações

As preferências do app (quais ferramentas estão desligadas, horário da
última sincronização) ficam em `~/.mcp-sync/settings.json`. Apagar esse
arquivo restaura o app para o estado padrão (todas as ferramentas
habilitadas).

## Perguntas frequentes

**O app modifica algo além da lista de servidores MCP?**
Não. Ele só toca na chave específica de servidores MCP de cada arquivo
(`mcpServers`, `servers`, `mcp_servers`, `context_servers` ou `mcp`,
dependendo da ferramenta) e preserva todo o resto do arquivo.

**Preciso configurar os caminhos dos arquivos manualmente?**
Não. O app varre automaticamente o sistema procurando por todas as
ferramentas suportadas e só mostra no menu as que encontrar instaladas.

**E se eu não quiser sincronizar uma ferramenta específica?**
Clique nela no menu para desligar. Ela deixa de ser lida/escrita até você
ligar de novo — o arquivo dela fica exatamente como estava na última
sincronização.

**Funciona sem internet?**
Sim, o app não faz nenhuma chamada de rede — é 100% local.

## Documentação completa (em inglês)

Veja [README.md](README.md) para a lista completa de ferramentas
suportadas, caminhos de configuração em cada sistema operacional,
instruções de desenvolvimento, e a seção "Function reference" com uma
tabela explicando, função por função, o que cada parte do código faz.
