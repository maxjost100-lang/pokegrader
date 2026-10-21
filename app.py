import json
import re
import requests
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="PokéGrader", page_icon="🃏")
st.title("🃏 PokéGrader")
st.caption("Estimation perso de la gradabilité et de la cote de tes cartes Pokémon")

if "GEMINI_API_KEY" not in st.secrets:
    st.error("Clé API manquante. Ajoute GEMINI_API_KEY dans les Secrets de Streamlit.")
    st.stop()

client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
MODELE = "gemini-2.5-flash"

PROMPT = """Tu es un expert en grading de cartes Pokémon (PSA, PCA, CGC, BGS).
Analyse la ou les images de cette carte et réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, avec ces clés:
{
  "nom_carte": "nom exact de la carte si identifiable",
  "extension": "nom de l'extension/set si identifiable",
  "numero": "numéro de la carte si visible",
  "centrage": {"note": 0-10, "commentaire": "..."},
  "coins": {"note": 0-10, "commentaire": "..."},
  "bords": {"note": 0-10, "commentaire": "..."},
  "surface": {"note": 0-10, "commentaire": "..."},
  "note_globale_estimee": 0-10,
  "fourchette_psa": "ex: 8-9",
  "gradable": true ou false,
  "defauts_visibles": ["liste des défauts"],
  "conseil": "faut-il l'envoyer en grading, et pourquoi",
  "limites": "ce que tu ne peux pas juger sur cette image"
}
Sois strict et réaliste, comme un vrai grader. Si l'image est floue ou mal cadrée, dis-le dans "limites"."""


def analyser(fichiers):
    contenu = []
    for f in fichiers:
        contenu.append(types.Part.from_bytes(data=f.getvalue(), mime_type=f.type or "image/jpeg"))
    contenu.append(PROMPT)
    rep = client.models.generate_content(model=MODELE, contents=contenu)
    match = re.search(r"\{.*\}", rep.text, re.DOTALL)
    return json.loads(match.group(0))


def chercher_prix(nom, numero):
    try:
        q = f'name:"{nom}"'
        if numero:
            q += f' number:"{numero.split("/")[0]}"'
        r = requests.get(
            "https://api.pokemontcg.io/v2/cards",
            params={"q": q, "pageSize": 5},
            timeout=15,
        )
        return r.json().get("data", [])
    except Exception:
        return []


fichiers = st.file_uploader(
    "Dépose le recto de ta carte (tu peux ajouter le verso)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

if fichiers:
    cols = st.columns(len(fichiers))
    for col, f in zip(cols, fichiers):
        col.image(f, use_container_width=True)

    if st.button("Analyser la carte", type="primary"):
        with st.spinner("Analyse en cours..."):
            try:
                res = analyser(fichiers)
            except Exception as e:
                st.error(f"Erreur pendant l'analyse: {e}")
                st.stop()

        st.subheader(f"{res.get('nom_carte', '?')} — {res.get('extension', '')}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Note estimée", f"{res.get('note_globale_estimee', '?')}/10")
        c2.metric("Fourchette PSA", res.get("fourchette_psa", "?"))
        c3.metric("Gradable ?", "Oui ✅" if res.get("gradable") else "Non ❌")

        st.write("### Détail")
        for cle in ["centrage", "coins", "bords", "surface"]:
            d = res.get(cle, {})
            st.write(f"**{cle.capitalize()}**: {d.get('note', '?')}/10 — {d.get('commentaire', '')}")

        if res.get("defauts_visibles"):
            st.write("### Défauts repérés")
            for d in res["defauts_visibles"]:
                st.write(f"- {d}")

        st.info(f"**Conseil**: {res.get('conseil', '')}")
        st.caption(f"Limites de l'analyse: {res.get('limites', '')}")

        st.write("### Cote estimée")
        cartes = chercher_prix(res.get("nom_carte", ""), res.get("numero", ""))
        if not cartes:
            st.warning("Aucun prix trouvé automatiquement. Vérifie sur Cardmarket ou eBay.")
        for c in cartes:
            st.write(f"**{c['name']}** — {c['set']['name']} n°{c['number']}")
            cm = c.get("cardmarket", {}).get("prices", {})
            tcp = c.get("tcgplayer", {}).get("prices", {})
            if cm:
                st.write(
                    f"Cardmarket: moyenne {cm.get('averageSellPrice', '?')} € "
                    f"| tendance {cm.get('trendPrice', '?')} € "
                    f"| bas {cm.get('lowPrice', '?')} €"
                )
            for variante, p in tcp.items():
                st.write(f"TCGplayer ({variante}): marché {p.get('market', '?')} $")
            st.divider()

        st.caption(
            "Pour savoir si le grading est rentable, compare le prix 'brut' ci-dessus avec "
            "les ventes récentes de la même carte en PSA 9 / PSA 10 sur eBay (filtre 'articles vendus')."
        )
