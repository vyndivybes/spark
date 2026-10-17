"""SPARK's fixed-route, no-key public API registry.

No scraping, arbitrary URL, private-address fetch, or paid service discovery.
These are narrow read-only lookups and never provide AI inference.
"""
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

REGISTRY=(
    {"id":"wikipedia","url":"https://en.wikipedia.org/api/rest_v1/page/summary/","provider":"Wikimedia"},
    {"id":"frankfurter","url":"https://api.frankfurter.dev/v2/rate/","provider":"Frankfurter"},
)
_WIKI=re.compile(r"^(?:wiki|wikipedia)\s+(.{1,160})$",re.I)
_FX=re.compile(r"^(?:convert|exchange)\s+([0-9]{1,9}(?:\.[0-9]{1,4})?)\s+([A-Za-z]{3})\s+(?:to|into)\s+([A-Za-z]{3})$",re.I)

def registry():
    return [dict(item) for item in REGISTRY]

async def public_api_answer(prompt, fetch):
    if not isinstance(prompt,str) or len(prompt)>250:
        return None
    prompt=prompt.strip()
    fx=_FX.fullmatch(prompt)
    if fx:
        amount,base,quote_code=fx.groups()
        base=base.lower()
        quote_code=quote_code.lower()
        if base==quote_code:
            return {"text":f"{amount} {base.upper()} equals {amount} {base.upper()}.","sources":[]}
        url=f"https://api.frankfurter.dev/v2/rate/{base}/{quote_code}"
        data=await fetch(url)
        if not isinstance(data,dict) or not isinstance(data.get("rate"),(int,float,str)):
            raise ValueError("No verified exchange rate is available.")
        try:
            result=Decimal(amount)*Decimal(str(data["rate"]))
        except InvalidOperation:
            raise ValueError("Provider returned an invalid rate.")
        when=data.get("date","latest published date")
        return {
            "text":f"{amount} {base.upper()} is approximately {result.quantize(Decimal('0.01'))} {quote_code.upper()} at the published rate on {when}.",
            "sources":[{"title":"Frankfurter exchange rate","url":url}]
        }
    wiki=_WIKI.fullmatch(prompt)
    if wiki:
        title=wiki.group(1).strip()
        if len(title)>160 or not re.fullmatch(r"[\w\s()'.,\-/]+",title,re.UNICODE):
            raise ValueError("Only a standard Wikipedia article title is accepted.")
        url="https://en.wikipedia.org/api/rest_v1/page/summary/"+quote(title.replace(" ","_"),safe="()_'-")
        data=await fetch(url)
        if not isinstance(data,dict) or not data.get("extract"):
            raise ValueError("Wikipedia did not return a summary.")
        heading=str(data.get("title",title))[:100]
        summary=str(data["extract"])[:1000]
        source="https://en.wikipedia.org/wiki/"+quote(title.replace(" ","_"),safe="()_'-")
        return {"text":f"{heading}: {summary}","sources":[{"title":heading+" — Wikipedia","url":source}]}
    return None
