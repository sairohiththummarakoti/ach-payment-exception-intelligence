"""Locally authored teaching notes, not a copy of the Nacha rulebook."""

import re

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

VERSION = "2026-11-05.1"
NOTES = {
    "controls": "Recalculate counts, routing entry hashes, credit totals and debit totals from the original records. A mismatch identifies inconsistent file evidence; it does not establish settlement or a return.",
    "structure": "The local teaching profile supports ordinary PPD and CCD entries without addenda. Check record length, ordering, mandatory metadata, routing checksum and date fields. Other profiles need a separately verified parser and procedure.",
    "duplicates": "A repeated fingerprint is the same uploaded file. A repeated trace or account, amount, direction and date is a probable duplicate requiring analyst comparison. Repeated amounts alone do not prove duplicate payment execution.",
    "review": "An analyst may approve, reject or escalate an exception disposition and may append a comment. Approval records a review decision only; it never fixes a malformed file, authorizes a payment or establishes settlement.",
    "R01": "R01 denotes insufficient funds. This code definition alone does not establish that a particular transaction was returned or that a retry is appropriate.",
    "R02": "R02 denotes account closed. Verify the source return evidence before drawing a transaction-specific conclusion.",
    "R03": "R03 denotes no account or unable to locate account. The definition is reference information, not confirmation of an account's status.",
    "R04": "R04 denotes invalid account number structure. Compare authorized evidence; do not infer customer identity or correct account details.",
    "R29": "R29 denotes a corporate customer advising that a debit is not authorized. This reference does not decide liability, entitlement or the validity of a dispute.",
}


class ProcedureRetriever(BaseRetriever):
    """Small deterministic LangChain lexical retriever with mandatory section routing."""

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked = sorted(
            NOTES,
            key=lambda key: (
                -(100 if key.lower() in tokens else 0)
                - len(tokens & set(re.findall(r"[a-z0-9]+", NOTES[key].lower()))),
                key,
            ),
        )
        return [
            Document(
                page_content=NOTES[key],
                metadata={"document": "ach-analyst-procedures", "version": VERSION, "section": key},
            )
            for key in ranked[:2]
        ]


def section_for(code: str) -> str:
    if "DUPLICATE" in code:
        return "duplicates"
    if any(word in code for word in ("TOTAL", "COUNT", "HASH", "CONTROL")):
        return "controls"
    return "structure"
