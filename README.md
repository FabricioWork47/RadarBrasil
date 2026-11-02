# Radar Brasil (automático e gratuito)

Todo dia útil, às 6h (Brasília), o GitHub coleta feeds RSS, pede a um modelo de IA gratuito (GitHub Models)
o resumo e a análise, e atualiza o site. Nas segundas, gera também a retrospectiva da semana.

## Instalação (uma vez, ~10 min)
1. Crie um repositório **público** no GitHub (ex.: `radar-brasil`) e envie estes arquivos mantendo as pastas.
2. Em **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main`, pasta `/docs`.
3. Em **Settings → Actions → General → Workflow permissions**: marque *Read and write permissions*.
4. Vá em **Actions → Atualizar Radar Brasil → Run workflow** para gerar a primeira edição.
5. Abra o log da execução: cada feed aparece como `[ok]` ou `[feed falhou]`. Troque no `FEEDS` de `scripts/gerar.py` os que falharem.
6. O site fica em `https://SEU-USUARIO.github.io/radar-brasil/`.

## Manutenção
- `docs/agenda.json`: agenda de eventos (Copom, IBGE, votações). Edite quando surgir evento novo.
- Modelo de IA: variável `MODELO` no script (padrão `openai/gpt-4o-mini`). Veja os modelos em github.com/marketplace/models.
- Se a IA estiver indisponível ou no limite gratuito, o site mostra só as manchetes, sem análise.

## Limites
- Os links vêm sempre dos feeds, nunca da IA. Itens sem fonte real não são publicados.
- A análise é gerada por IA: pode errar. Confira nas fontes.
- O Valor Econômico é pago e não tem feed aberto, por isso não entra na coleta.
