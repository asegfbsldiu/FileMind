"""New local adapter protocol checks; the server is a generated test double."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from filemind.ai.adapters import _fetch_ollama_tags, build_provider
from filemind.ai.model_config import ModelConfig
from filemind.ai.openai_compatible import AIServiceError, OpenAICompatibleClient
from filemind.storage.settings import AISettings


class GeneratedHandler(BaseHTTPRequestHandler):
    """Serve only generated tags and a labeled compatibility answer."""

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.server.paths.append(self.path)
        self._respond({"models": [{"name": "fixture:latest"}, {"name": "fixture-two:small"}]})

    def do_POST(self) -> None:
        self.server.paths.append(self.path)
        count = int(self.headers["Content-Length"])
        self.server.request = json.loads(self.rfile.read(count))
        self._respond({"id": "generated", "object": "chat.completion", "created": 0,
                       "model": "fixture", "choices": [{"index": 0, "finish_reason": "stop",
                       "message": {"role": "assistant", "content": "Generated protocol fixture"}}]})

    def _respond(self, payload: object) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def test_local_discovery_and_openai_chat_use_the_expected_http_paths() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), GeneratedHandler)
    server.paths = []
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        provider = build_provider(ModelConfig("ollama", "fixture", base_url=base))
        assert provider.list_models() == ["fixture", "fixture-two:small"]
        answer = provider.chat([{"role": "user", "content": "Generated question"}], {"system": "Fixture system"})
        assert answer.content == "Generated protocol fixture"
        assert answer.ok
        assert server.paths == ["/api/tags", "/v1/chat/completions"]
        assert server.request["model"] == "fixture"
        assert server.request["messages"][0] == {"role": "system", "content": "Fixture system"}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    assert not worker.is_alive()


def test_local_discovery_rejects_remote_hosts_and_redirects() -> None:
    with pytest.raises(AIServiceError, match="仅允许"):
        _fetch_ollama_tags("https://other.example/api/tags", 5)
    from filemind.ai.adapters import _NoRedirect
    with pytest.raises(AIServiceError, match="重定向"):
        _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example")


@pytest.mark.parametrize("payload", [{}, {"models": "invalid"}])
def test_invalid_tags_are_not_reported_as_successful_discovery(payload: object) -> None:
    with patch("filemind.ai.adapters._fetch_ollama_tags", return_value=payload):
        provider = build_provider(ModelConfig("ollama", "fixture"))
        with pytest.raises(AIServiceError, match="响应格式"):
            provider.list_models()


def test_cancelled_stream_closes_transport_and_never_yields_reasoning() -> None:
    cancellation = Event()
    chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="answer", reasoning_content="private"))])]

    class GeneratedStream:
        closed = False

        def __iter__(self):
            yield from chunks
            cancellation.set()
            yield from chunks

        def close(self) -> None:
            self.closed = True

    stream = GeneratedStream()
    with patch("filemind.ai.openai_compatible.OpenAI") as sdk:
        sdk.return_value.chat.completions.create.return_value = stream
        client = OpenAICompatibleClient(AISettings("ollama", "http://127.0.0.1:11434/v1", "fixture", 10))
        replies = client.stream([{"role": "user", "content": "Generated"}], cancellation)
        assert next(replies) == "answer"
        with pytest.raises(InterruptedError):
            next(replies)
    assert stream.closed
