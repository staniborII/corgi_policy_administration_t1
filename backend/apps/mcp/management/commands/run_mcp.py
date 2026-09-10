from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start the Corgi MCP server (stdio transport)."

    def handle(self, *args, **options):
        from apps.mcp.server import mcp

        self.stdout.write("Starting Corgi MCP server...")
        mcp.run()
