#!/usr/bin/env python3
"""
Canopy CLI - Command Line Interface
The jungle listens to your commands.
"""
import argparse
import sys
import json
from pathlib import Path
import base64
import hashlib

from canopy import CanopyRenderer, Archive
from canopy.session import get_session_manager, SessionEvent, EventType
from canopy.hashing import hash_manifest, hash_event_log, hash_pixels
from canopy.manifest import ManifestBuilder


def cmd_render(args):
    """Render a frame or animation."""
    renderer = CanopyRenderer(
        width=args.width,
        height=args.height,
        seed=args.seed
    )
    
    # Enable effects
    for effect in args.effects:
        renderer.effects.enable(effect)
    
    # Apply preset if specified
    if args.preset:
        renderer.apply_preset(args.preset)
    
    # Apply grid deformation
    if args.grid:
        if args.grid == "kaleidoscope":
            renderer.grid.add_kaleidoscope()
        elif args.grid == "wave":
            renderer.grid.add_wave(amplitude=0.02, frequency=10)
        elif args.grid == "turbulence":
            renderer.grid.add_turbulence()
    
    if args.frames > 1:
        # Render animation
        print(f"Rendering {args.frames} frames...")
        frames = renderer.render_animation(
            frames=args.frames,
            fps=args.fps,
            effect_chain=args.effects
        )
        
        output_path = Path(args.output)
        if args.format == "gif":
            renderer.save_animation(frames, str(output_path), format="gif")
        else:
            renderer.save_animation(frames, str(output_path), format="mp4")
        
        print(f"Animation saved to {args.output}")
    else:
        # Render single frame
        frame = renderer.render_frame()
        img = renderer.to_image(frame, args.output)
        print(f"Frame saved to {args.output}")
        
        # Also print seed for reproducibility
        print(f"Sacred seed: {renderer.rng.seed}")


def cmd_archive(args):
    """Archive operations."""
    archive = Archive(args.db or "canopy_archive.db")
    
    if args.archive_cmd == "save":
        # Load config from file
        with open(args.config_file) as f:
            config = json.load(f)
        
        entry_id = archive.save_state(
            name=args.name,
            state=config,
            tags=args.tags.split(",") if args.tags else None
        )
        print(f"Saved as entry #{entry_id}")
    
    elif args.archive_cmd == "load":
        state = archive.load_state(args.entry_id)
        if state:
            print(json.dumps(state, indent=2))
        else:
            print(f"Entry #{args.entry_id} not found")
    
    elif args.archive_cmd == "search":
        results = archive.search(
            query=args.query,
            limit=args.limit
        )
        print(f"Found {len(results)} entries:")
        for r in results:
            print(f"  #{r['id']}: {r['name']} (seed: {r['seed']})")
    
    elif args.archive_cmd == "list":
        entries = archive.get_recent(args.limit)
        print(f"Recent entries:")
        for e in entries:
            print(f"  #{e['id']}: {e['name']} - {e['created_at']}")
    
    elif args.archive_cmd == "stats":
        stats = archive.get_stats()
        print("Archive Statistics:")
        for key, val in stats.items():
            print(f"  {key}: {val}")


def cmd_session(args):
    """Session operations."""
    from canopy.hashing import hash_session_export as compute_export_hash
    session_manager = get_session_manager()
    
    if args.session_cmd == "create":
        # Create a new session
        builder = ManifestBuilder(
            seed=args.seed,
            width=args.width,
            height=args.height
        )
        if args.preset:
            builder = builder.with_preset(args.preset)
        manifest = builder.build()
        
        session = session_manager.create_session(manifest)
        print(f"Session created: {session.session_id}")
        print(f"Manifest hash: {hash_manifest(session.base_manifest)}")
    
    elif args.session_cmd == "event":
        # Apply an event to a session
        session = session_manager.get_session(args.session_id)
        if not session:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)
        
        # Load payload from file or parse
        if args.payload_file:
            with open(args.payload_file) as f:
                payload = json.load(f)
        else:
            payload = {}
        
        event = SessionEvent(
            event_index=len(session.events),
            event_type=EventType(args.event_type),
            payload=payload
        )
        
        success, error = session_manager.apply_event(args.session_id, event)
        if success:
            print(f"Event #{event.event_index} applied")
            print(f"Manifest hash: {event.manifest_hash_after}")
        else:
            print(f"Failed: {error}", file=sys.stderr)
            sys.exit(1)
    
    elif args.session_cmd == "render":
        # Render a session frame
        session = session_manager.get_session(args.session_id)
        if not session:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)
        
        frame, pixel_hash = session_manager.render_session_frame(
            session, args.frame, args.width, args.height
        )
        session.latest_pixel_hash = pixel_hash
        
        # Save to file
        img = (frame * 255).astype("uint8")
        from PIL import Image
        Image.fromarray(img).save(args.output)
        print(f"Frame saved to {args.output}")
        print(f"Pixel hash: {pixel_hash}")
        print(f"Manifest hash: {hash_manifest(session.current_manifest)}")
    
    elif args.session_cmd == "rewind":
        # Rewind session to an event
        success, error = session_manager.rewind_session(args.session_id, args.event)
        if success:
            print(f"Rewound to event {args.event}")
            session = session_manager.get_session(args.session_id)
            print(f"Manifest hash: {hash_manifest(session.current_manifest)}")
        else:
            print(f"Failed: {error}", file=sys.stderr)
            sys.exit(1)
    
    elif args.session_cmd == "fork":
        # Fork a session
        fork, error = session_manager.fork_session(args.session_id, args.event)
        if fork:
            print(f"Fork created: {fork.session_id}")
            print(f"Parent: {fork.parent_session_id}")
            print(f"Fork event: {fork.fork_event_index}")
            print(f"Manifest hash: {hash_manifest(fork.current_manifest)}")
        else:
            print(f"Failed: {error}", file=sys.stderr)
            sys.exit(1)
    
    elif args.session_cmd == "export":
        # Export session
        export_data = session_manager.export_session(args.session_id)
        if export_data:
            export_data["export_hash"] = compute_export_hash(export_data)
            if args.output:
                with open(args.output, "w") as f:
                    json.dump(export_data, f, indent=2)
                print(f"Exported to {args.output}")
            else:
                print(json.dumps(export_data, indent=2))
        else:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)
    
    elif args.session_cmd == "import":
        # Import session
        with open(args.session_file) as f:
            payload = json.load(f)
        
        session, error = session_manager.import_session(payload)
        if session:
            print(f"Imported: {session.session_id}")
            print(f"Manifest hash: {hash_manifest(session.current_manifest)}")
        else:
            print(f"Failed: {error}", file=sys.stderr)
            sys.exit(1)
    
    elif args.session_cmd == "verify":
        # Verify session integrity
        is_valid, errors = session_manager.verify_session_integrity(args.session_id)
        if is_valid:
            print(f"Session {args.session_id} is valid")
        else:
            print(f"Session {args.session_id} has errors:")
            for err in errors:
                print(f"  - {err}")
            sys.exit(1)
    
    elif args.session_cmd == "info":
        # Get session info
        session = session_manager.get_session(args.session_id)
        if not session:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)
        
        print(f"Session ID: {session.session_id}")
        print(f"Status: {session.status.value}")
        print(f"Base manifest hash: {hash_manifest(session.base_manifest)}")
        print(f"Current manifest hash: {hash_manifest(session.current_manifest)}")
        print(f"Event log hash: {hash_event_log(session.events)}")
        print(f"Events: {len(session.events)}")
        print(f"Current frame: {session.current_frame}")
        if session.parent_session_id:
            print(f"Parent: {session.parent_session_id}")
            print(f"Fork event: {session.fork_event_index}")
    
    elif args.session_cmd == "close":
        # Close session
        success = session_manager.close_session(args.session_id)
        if success:
            print(f"Session {args.session_id} closed")
        else:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)
    
    elif args.session_cmd == "archive":
        # Archive session
        from canopy.archive.database import SessionArchive
        archive = SessionArchive()
        
        session = session_manager.get_session(args.session_id)
        if not session:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)
        
        entry_id = archive.save_session(session)
        print(f"Session archived as entry #{entry_id}")
        
        # Close session after archiving
        session_manager.close_session(args.session_id)
        print(f"Session {args.session_id} closed")


def cmd_server(args):
    """Start the FastAPI server."""
    import uvicorn
    from server import app
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload
    )


def main():
    parser = argparse.ArgumentParser(
        description="The Deterministic Jungle Canopy 🦜🌿"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Render command
    render_parser = subparsers.add_parser("render", help="Render frames")
    render_parser.add_argument("--seed", type=int, default=42, help="Sacred seed")
    render_parser.add_argument("--width", type=int, default=1280)
    render_parser.add_argument("--height", type=int, default=720)
    render_parser.add_argument("--output", "-o", default="output.png")
    render_parser.add_argument("--frames", "-f", type=int, default=1)
    render_parser.add_argument("--fps", type=int, default=30)
    render_parser.add_argument("--format", choices=["png", "gif", "mp4"], default="png")
    render_parser.add_argument("--effects", "-e", nargs="+", default=[])
    render_parser.add_argument("--preset", "-p", choices=[
        "solaris_dream", "glitch_cathedral", "tropical_night",
        "vhs_prophecy", "sacred_geometry", "chaos_realm",
        "serenity", "neon_jungle", "ancient_scroll", "prismatic"
    ])
    render_parser.add_argument("--grid", choices=["kaleidoscope", "wave", "turbulence"])
    render_parser.set_defaults(func=cmd_render)
    
    # Archive command
    archive_parser = subparsers.add_parser("archive", help="Archive operations")
    archive_parser.add_argument("--db", help="Archive database path")
    archive_subparsers = archive_parser.add_subparsers(dest="archive_cmd")
    
    save_parser = archive_subparsers.add_parser("save", help="Save to archive")
    save_parser.add_argument("name", help="Entry name")
    save_parser.add_argument("config_file", help="Config JSON file")
    save_parser.add_argument("--tags", help="Comma-separated tags")
    
    load_parser = archive_subparsers.add_parser("load", help="Load from archive")
    load_parser.add_argument("entry_id", type=int)
    
    search_parser = archive_subparsers.add_parser("search", help="Search archive")
    search_parser.add_argument("--query", "-q")
    search_parser.add_argument("--limit", "-n", type=int, default=20)
    
    list_parser = archive_subparsers.add_parser("list", help="List recent")
    list_parser.add_argument("--limit", "-n", type=int, default=10)
    
    stats_parser = archive_subparsers.add_parser("stats", help="Show stats")
    
    archive_parser.set_defaults(func=cmd_archive)
    
    # Session command
    session_parser = subparsers.add_parser("session", help="Session operations")
    session_subparsers = session_parser.add_subparsers(dest="session_cmd")
    
    create_parser = session_subparsers.add_parser("create", help="Create session")
    create_parser.add_argument("--seed", type=int, default=42)
    create_parser.add_argument("--width", type=int, default=128)
    create_parser.add_argument("--height", type=int, default=128)
    create_parser.add_argument("--preset", "-p")
    
    event_parser = session_subparsers.add_parser("event", help="Apply event")
    event_parser.add_argument("session_id", help="Session ID")
    event_parser.add_argument("--type", dest="event_type", required=True,
                            help="Event type (set_seed, apply_preset, set_effect, etc.)")
    event_parser.add_argument("--payload", dest="payload_file", 
                            help="JSON file with event payload")
    
    render_parser = session_subparsers.add_parser("render", help="Render frame")
    render_parser.add_argument("session_id", help="Session ID")
    render_parser.add_argument("frame", type=int, help="Frame index")
    render_parser.add_argument("--output", "-o", default="frame.png")
    render_parser.add_argument("--width", type=int, default=128)
    render_parser.add_argument("--height", type=int, default=128)
    
    rewind_parser = session_subparsers.add_parser("rewind", help="Rewind session")
    rewind_parser.add_argument("session_id", help="Session ID")
    rewind_parser.add_argument("event", type=int, help="Event index to rewind to")
    
    fork_parser = session_subparsers.add_parser("fork", help="Fork session")
    fork_parser.add_argument("session_id", help="Session ID")
    fork_parser.add_argument("event", type=int, help="Event index to fork from")
    
    export_parser = session_subparsers.add_parser("export", help="Export session")
    export_parser.add_argument("session_id", help="Session ID")
    export_parser.add_argument("--output", "-o", help="Output file")
    
    import_parser = session_subparsers.add_parser("import", help="Import session")
    import_parser.add_argument("session_file", help="Session JSON file")
    
    verify_parser = session_subparsers.add_parser("verify", help="Verify session")
    verify_parser.add_argument("session_id", help="Session ID")
    
    info_parser = session_subparsers.add_parser("info", help="Session info")
    info_parser.add_argument("session_id", help="Session ID")
    
    close_parser = session_subparsers.add_parser("close", help="Close session")
    close_parser.add_argument("session_id", help="Session ID")
    
    archive_session_parser = session_subparsers.add_parser("archive", help="Archive session")
    archive_session_parser.add_argument("session_id", help="Session ID")
    
    session_parser.set_defaults(func=cmd_session)
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start API server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", type=int, default=8000)
    server_parser.add_argument("--reload", action="store_true")
    server_parser.set_defaults(func=cmd_server)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
