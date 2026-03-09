.PHONY: inspect install

inspect:
	npx @modelcontextprotocol/inspector uv run dylogy.py

install:
	claude mcp add dylogy \
		-s user \
		-e DYLOGY_API_BASE \
		-e DYLOGY_EMAIL \
		-e DYLOGY_PASSWORD \
		-- uv run --directory $(CURDIR) dylogy.py