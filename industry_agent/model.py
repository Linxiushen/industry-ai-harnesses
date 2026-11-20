"""Request a tool plan from a locally served, OpenAI-compatible chat model."""

import http.client
import json


class LocalModelPlanner:
    """Single inference call on loopback. Only the prompt and tool catalog are sent."""

    def __init__(self, model, port=11434):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Specify the name of a model already served locally.")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("The local model port must be between 1 and 65535.")
        self.model = model.strip()
        self.port = port

    def __call__(self, request, catalog):
        schema = {
            "type": "object",
            "properties": {
                "domain": {"enum": [*sorted({t["domain"] for t in catalog}), None]},
                "tools": {"type": "array", "items": {"enum": [t["id"] for t in catalog]},
                          "uniqueItems": True, "maxItems": 3},
                "query": {"type": "string"},
                "country": {"type": "string"},
            },
            "required": ["domain", "tools"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model, "temperature": 0, "stream": False, "max_tokens": 384,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "industry_tool_plan", "schema": schema,
            }},
            "messages": [
                {"role": "system", "content": (
                    "Plan the requested analysis using the supplied tool catalog. "
                    "Choose one domain and list the tools needed in order. "
                    "For an ambiguous or unsupported request return a null domain and empty tools. "
                    "Use query or country only for clinical operations, with values from the request. "
                    "Return only the JSON plan. Catalog: " + json.dumps(catalog, ensure_ascii=False)
                )},
                {"role": "user", "content": request},
            ],
        }
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            conn.request("POST", "/v1/chat/completions", json.dumps(payload).encode("utf-8"),
                         {"Content-Type": "application/json", "Accept": "application/json"})
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError(f"Local model returned HTTP {response.status}. "
                                 "Check the model name and structured-output support.")
            body = response.read(65537)
        except (OSError, http.client.HTTPException) as exc:
            raise ValueError(f"Cannot reach the local model at 127.0.0.1:{self.port}: {exc}") from exc
        finally:
            conn.close()
        if len(body) > 65536:
            raise ValueError("Local model response exceeded 64 KiB.")
        try:
            choice = json.loads(body)["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ValueError("The local model truncated its tool plan.")
            plan = json.loads(choice["message"]["content"])
        except (ValueError, LookupError, AttributeError, TypeError) as exc:
            raise ValueError("Local model did not produce a complete JSON tool plan.") from exc
        if not isinstance(plan, dict):
            raise ValueError("Local model tool plan must be a JSON object.")
        return plan
