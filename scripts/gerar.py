#!/usr/bin/env python3
"""Radar Brasil: coleta RSS, resume com IA (GitHub Models, gratuito) e grava JSON em docs/data/.
Só usa a biblioteca padrão do Python. Se a IA falhar, publica só as manchetes (sem análise)."""
import json, os, re, sys, html, time, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BRT = timezone(timedelta(hours=-3))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
MODELO = os.environ.get("MODELO", "openai/gpt-4o-mini")
ENDPOINT = "https://models.github.ai/inference/chat/completions"
JANELA_H = 40          # notícias das últimas 40 h
MAX_CAND = 60          # candidatas enviadas à IA

# (nome, url, filtrar_por_palavra_chave). Feeds que falharem são só ignorados (veja o log).
FEEDS = [
    ("g1 Economia", "https://g1.globo.com/rss/g1/economia/", False),
    ("g1 Política", "https://g1.globo.com/rss/g1/politica/", False),
    ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", True),
    ("InfoMoney", "https://www.infomoney.com.br/feed/", True),
    ("Money Times", "https://www.moneytimes.com.br/feed/", True),
    ("CNN Brasil Economia", "https://www.cnnbrasil.com.br/economia/feed/", False),
    ("Agência Senado", "https://www12.senado.leg.br/noticias/rss", True),
    ("Agência Câmara", "https://www.camara.leg.br/noticias/rss/ultimas-noticias", True),
    ("Poder360", "https://www.poder360.com.br/feed/", True),
]
PALAVRAS = re.compile(r"economi|selic|copom|juros|infla|ipca|pib|d[óo]lar|ibovespa|bolsa|fiscal|or[çc]amento|"
                      r"tribut|imposto|reforma|banco central|tesouro|d[ée]ficit|d[íi]vida|governo|congresso|"
                      r"senado|c[âa]mara|stf|lula|ministro|pec|emprego|desemprego|ibge|petr[óo]leo|agro|"
                      r"exporta|importa|balan[çc]a|energia|aneel|elei[çc]", re.I)

def log(*a): print(*a, file=sys.stderr, flush=True)

def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "RadarBrasil/1.0 (+github pages)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()

def limpar(t, n=320):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n].rsplit(" ", 1)[0] + "…" if len(t) > n else t

def tag(e): return e.tag.rsplit("}", 1)[-1].lower()

def data_item(txt):
    if not txt: return None
    try:
        d = parsedate_to_datetime(txt)
    except Exception:
        try: d = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        except Exception: return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def parse_feed(xml_bytes, fonte):
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter():
        if tag(it) not in ("item", "entry"): continue
        f = {tag(c): c for c in it}
        titulo = limpar((f["title"].text if "title" in f else ""), 200)
        link = ""
        if "link" in f:
            link = (f["link"].text or "").strip() or f["link"].attrib.get("href", "")
        desc = ""
        for k in ("description", "summary", "content"):
            if k in f and f[k].text: desc = limpar(f[k].text); break
        d = None
        for k in ("pubdate", "published", "updated", "date"):
            if k in f and f[k].text: d = data_item(f[k].text.strip()); break
        if titulo and link.startswith("http") and d:
            out.append({"fonte": fonte, "titulo": titulo, "resumo": desc, "link": link, "data": d})
    return out

def coletar(agora):
    itens = []
    for nome, url, filtra in FEEDS:
        try:
            got = parse_feed(baixar(url), nome)
        except Exception as e:
            log(f"[feed falhou] {nome}: {e}"); continue
        n0 = len(got)
        got = [g for g in got if agora - g["data"] <= timedelta(hours=JANELA_H)]
        if filtra: got = [g for g in got if PALAVRAS.search(g["titulo"] + " " + g["resumo"])]
        log(f"[ok] {nome}: {n0} itens, {len(got)} úteis")
        itens += got
    vistos, final = set(), []
    for g in sorted(itens, key=lambda x: x["data"], reverse=True):
        k = re.sub(r"\W+", "", g["titulo"].lower())[:45]
        if k in vistos: continue
        vistos.add(k); final.append(g)
    return final[:MAX_CAND]

def chamar_ia(sistema, usuario):
    token = os.environ.get("GITHUB_TOKEN")
    if not token: raise RuntimeError("sem GITHUB_TOKEN")
    corpo = json.dumps({"model": MODELO, "temperature": 0.2, "max_tokens": 3500,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}).encode()
    for tentativa in range(3):
        req = urllib.request.Request(ENDPOINT, data=corpo, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = json.load(r)["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", txt, re.S)
            return json.loads(m.group(0))
        except urllib.error.HTTPError as e:
            log(f"[IA] HTTP {e.code} (tentativa {tentativa+1})")
            if e.code in (429, 500, 502, 503): time.sleep(20 * (tentativa + 1)); continue
            raise
    raise RuntimeError("IA indisponível")

REGRAS = ("Você é analista de economia e política do Brasil. Escreva em português do Brasil, tom claro e neutro. "
          "Use SOMENTE as informações da lista fornecida: não invente números, datas, nomes nem fatos. "
          "Separe fato (campo 'resumo') de interpretação (campos 'contexto' e 'impacto'). "
          "'impacto' é sempre hipótese: use 'pode', 'tende a', 'possível'. Nunca dê recomendação de investimento. "
          "Cada item deve citar 'indices' (números da lista) que o sustentam. Responda apenas com JSON.")

def anexar(itens, pool):
    saida = []
    for it in itens or []:
        idx = [i for i in it.get("indices", []) if isinstance(i, int) and 0 <= i < len(pool)]
        fontes, vistos = [], set()
        for i in idx:
            for f in pool[i]["fontes"]:
                if f["u"] not in vistos: vistos.add(f["u"]); fontes.append(f)
        if not fontes: continue            # sem fonte real, não publica
        it = {k: str(it.get(k, "")) for k in ("tag", "titulo", "resumo", "contexto", "impacto")}
        it["fontes"] = fontes[:4]; saida.append(it)
    return saida

def gerar_dia(cands):
    pool = [{"fontes": [{"n": c["fonte"], "u": c["link"]}]} for c in cands]
    lista = "\n".join(f"[{i}] ({c['fonte']}) {c['titulo']} — {c['resumo']}" for i, c in enumerate(cands))
    r = chamar_ia(REGRAS, "Notícias recentes:\n" + lista + "\n\nEscolha as 8 a 12 mais relevantes de economia e política "
        "nacional e agrupe duplicatas. Formato: {\"resumo30s\":[3 a 5 frases curtas],\"itens\":[{\"tag\":\"Economia|Política|"
        "Fiscal|Juros e inflação|Congresso|Judiciário|...\",\"titulo\":\"...\",\"resumo\":\"fato em 2-3 frases\","
        "\"contexto\":\"por que importa\",\"impacto\":\"possível efeito (hipótese)\",\"indices\":[0]}]}")
    return {"resumo30s": [str(x) for x in r.get("resumo30s", [])][:5], "itens": anexar(r.get("itens"), pool), "ia": True}

def dia_sem_ia(cands):
    its = [{"tag": c["fonte"], "titulo": c["titulo"], "resumo": c["resumo"], "contexto": "", "impacto": "",
            "fontes": [{"n": c["fonte"], "u": c["link"]}]} for c in cands[:15]]
    return {"resumo30s": ["Análise por IA indisponível hoje: exibindo apenas as manchetes coletadas."], "itens": its, "ia": False}

def gerar_semana(hoje):
    pool, linhas = [], []
    for k in range(1, 8):
        p = DATA / f"{(hoje - timedelta(days=k)).isoformat()}.json"
        if not p.exists(): continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for it in d.get("dia", {}).get("itens", []):
            pool.append({"fontes": it["fontes"]})
            linhas.append(f"[{len(pool)-1}] ({d['data']}) {it['titulo']} — {it['resumo']}")
    if len(pool) < 5: return None
    r = chamar_ia(REGRAS, "Itens publicados nos últimos 7 dias:\n" + "\n".join(linhas) + "\n\nFaça a retrospectiva da semana. "
        "Formato: {\"resumo\":[4 a 6 frases],\"destaques\":[{\"tag\":\"...\",\"titulo\":\"...\",\"resumo\":\"o que aconteceu\","
        "\"contexto\":\"consequências possíveis\",\"impacto\":\"hipótese\",\"indices\":[0]}]} com 5 a 8 destaques.")
    ini, fim = hoje - timedelta(days=7), hoje - timedelta(days=1)
    return {"intervalo": f"{ini.strftime('%d/%m')} a {fim.strftime('%d/%m/%Y')}",
            "resumo": [str(x) for x in r.get("resumo", [])][:6], "destaques": anexar(r.get("destaques"), pool)}

def main():
    agora = datetime.now(timezone.utc); hoje = agora.astimezone(BRT).date()
    DATA.mkdir(parents=True, exist_ok=True)
    cands = coletar(agora)
    if len(cands) < 3: log("Poucas notícias coletadas; abortando sem sobrescrever."); sys.exit(0)
    try: dia = gerar_dia(cands)
    except Exception as e:
        log(f"[IA falhou] {e}"); dia = dia_sem_ia(cands)
    if not dia["itens"]: dia = dia_sem_ia(cands)
    semana = None
    if hoje.weekday() == 0 and dia.get("ia"):
        try: semana = gerar_semana(hoje)
        except Exception as e: log(f"[semana falhou] {e}")
    saida = {"data": hoje.isoformat(), "geradoEm": datetime.now(BRT).strftime("%d/%m/%Y %H:%M"),
             "modelo": MODELO if dia.get("ia") else None, "dia": dia, "semana": semana}
    (DATA / f"{hoje.isoformat()}.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    datas = sorted((p.stem for p in DATA.glob("20*.json")), reverse=True)[:120]
    (DATA / "index.json").write_text(json.dumps(datas), encoding="utf-8")
    log(f"Edição {hoje} gravada: {len(dia['itens'])} itens, IA={dia.get('ia')}, semana={'sim' if semana else 'não'}")

if __name__ == "__main__": main()
