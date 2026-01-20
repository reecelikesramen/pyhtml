"""Development server with hot reload."""
from pathlib import Path

import uvicorn



def _generate_cert():
    """Generate self-signed certificate for localhost."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import datetime
    import tempfile
    import os

    # Use ECDSA P-256 (More standard for QUIC/TLS 1.3 than RSA)
    key = ec.generate_private_key(ec.SECP256R1())

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])

    import ipaddress

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        # Backdate by 1 hour to handle minor clock skew
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    ).not_valid_after(
        # Valid for 10 days (Required for WebTransport serverCertificateHashes)
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(u"localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.IPAddress(ipaddress.IPv6Address("::1")),
        ]),
        critical=False,
    ).sign(key, hashes.SHA256())

    cert_dir = tempfile.mkdtemp()
    cert_path = os.path.join(cert_dir, "cert.pem")
    key_path = os.path.join(cert_dir, "key.pem")

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    fingerprint = cert.fingerprint(hashes.SHA256())
    
    return cert_path, key_path, fingerprint


async def run_dev_server(host: str, port: int, reload: bool, pages_dir: Path):
    """Run development server with hot reload."""
    from pyhtml.runtime.server import create_app
    import asyncio
    import signal
    import logging
    from watchfiles import awatch
    
    # Configure logging to see Hypercorn/aioquic debug output
    logging.basicConfig(level=logging.INFO)  # Reduced from DEBUG to avoid spam
    logging.getLogger("hypercorn").setLevel(logging.INFO)
    
    # Try to import Hypercorn for HTTP/3 support
    try:
        from hypercorn.asyncio import serve
        from hypercorn.config import Config
        import aioquic
        HAS_HTTP3 = True
    except ImportError:
        HAS_HTTP3 = False
    
    
    if not HAS_HTTP3:
        print("PyHTML: HTTP/3 (WebTransport) disabled. Install 'aioquic' and 'hypercorn' to enable.")

    # Create shutdown event
    shutdown_event = asyncio.Event()

    async def _handle_signal():
        print("\nPyHTML: Shutting down...")
        shutdown_event.set()

    # Register signal handlers
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(_handle_signal()))
    except NotImplementedError:
        pass

    # Create app instance
    app = create_app(pages_dir, reload=reload)
    
    # Watcher task
    async def watch_changes():
        try:
            # Determine pyhtml source directory
            import pyhtml
            pyhtml_src_dir = Path(pyhtml.__file__).parent
            
            # Watch both pages and source
            async for changes in awatch(pages_dir, pyhtml_src_dir, stop_event=shutdown_event):
                # Check what changed
                library_changed = False
                for change_type, file_path in changes:
                    if str(file_path).startswith(str(pyhtml_src_dir)):
                        library_changed = True
                        break
                
                if library_changed:
                     print("PyHTML: Library code changed, restarting server...")
                     # Signal shutdown to trigger restart (managed by outer loop in future, 
                     # but for now we just exit so user can rely on tools like nodemon/watchdog or 
                     # we can try to re-exec).
                     # Since we are inside the app process, we can't easily re-exec self cleanly 
                     # without losing the socket ownership if not careful.
                     # BUT, users usually run this via `python -m pyhtml.cli` which might not have a watcher wrapper.
                     
                     # Simple approach: Exit with a specific code or just print message?
                     # Standard Uvicorn reload works by spawning a subprocess. We are running in-process here.
                     
                     # Check if we can just trigger a reload of modules? Unlikely to work well.
                     
                     # Wait, if we are running in `dev` command, we might be inside a reloader?
                     # No, we disabled uvicorn reloader `config.use_reloader = False`.
                     
                     # If we want full reload on library changes, we should probably let Uvicorn manage it
                     # or implement a re-exec.
                     
                     # For now, let's just create a marker file or print a loud message. 
                     # Actually, if we just want to reload pages, we do that below. 
                     # But for `page.py` changes (base class), we need a restart.
                     
                     print("!!! Library change detected. Please restart server manually for now (Ctrl+C and run again) until auto-restart is implemented. !!!")
                     
                # First, recompile changed pages
                # First, recompile changed pages
                should_reload = False
                for change_type, file_path in changes:
                    if file_path.endswith('.pyhtml'):
                        should_reload = True
                        if hasattr(app.state, 'pyhtml_app'):
                           try:
                               app.state.pyhtml_app.reload_page(Path(file_path))
                           except Exception as e:
                               print(f"Error reloading page: {e}")

                # Then broadcast reload if needed
                if should_reload:
                    print(f"PyHTML: Changes detected in {pages_dir}, reloading clients...")
                    
                    # Broadcast reload to WebSocket clients
                    if hasattr(app.state, 'ws_handler'):
                        await app.state.ws_handler.broadcast_reload()
                    
                    # Broadcast reload to HTTP polling clients
                    if hasattr(app.state, 'http_handler'):
                        app.state.http_handler.broadcast_reload()
                    
                    # Broadcast to WebTransport clients
                    if hasattr(app.state, 'web_transport_handler'):
                        await app.state.web_transport_handler.broadcast_reload()
                        
        except Exception as e:
            if not shutdown_event.is_set():
                print(f"Watcher error: {e}")
                import traceback
                traceback.print_exc()

    async with asyncio.TaskGroup() as tg:
        if HAS_HTTP3:
            try:
                # Check for existing trusted certificates (e.g. from mkcert)
                # mkcert localhost -> localhost.pem, localhost-key.pem
                # Check for existing trusted certificates (e.g. from mkcert)
                # mkcert localhost -> localhost.pem, localhost-key.pem
                potential_certs = [
                    (Path("localhost+2.pem"), Path("localhost+2-key.pem")),
                    (Path("localhost.pem"), Path("localhost-key.pem")),
                    (Path("cert.pem"), Path("key.pem")),
                ]
                
                cert_path, key_path = None, None
                for c_file, k_file in potential_certs:
                    if c_file.exists() and k_file.exists():
                        print(f"PyHTML: Found local certificates ({c_file}), using them.")
                        
                        # For QUIC/HTTP3, we need the full certificate chain
                        # mkcert stores its CA at ~/Library/Application Support/mkcert/rootCA.pem (macOS)
                        # or ~/.local/share/mkcert/rootCA.pem (Linux)
                        import os
                        import tempfile
                        
                        mkcert_ca_paths = [
                            Path.home() / "Library" / "Application Support" / "mkcert" / "rootCA.pem",  # macOS
                            Path.home() / ".local" / "share" / "mkcert" / "rootCA.pem",  # Linux
                        ]
                        
                        ca_cert = None
                        for ca_path in mkcert_ca_paths:
                            if ca_path.exists():
                                ca_cert = ca_path.read_text()
                                print(f"PyHTML: Found mkcert CA, creating certificate chain for QUIC...")
                                break
                        
                        if ca_cert:
                            # Create a chain file: leaf cert + CA cert
                            leaf_cert = c_file.read_text()
                            chain_content = leaf_cert + "\n" + ca_cert
                            
                            # Write to temp file
                            chain_dir = tempfile.mkdtemp()
                            chain_path = os.path.join(chain_dir, "chain.pem")
                            with open(chain_path, "w") as f:
                                f.write(chain_content)
                            
                            cert_path = chain_path
                        else:
                            cert_path = str(c_file)
                        
                        key_path = str(k_file)
                        
                        # Calculate cert hash for WebTransport options
                        # This ensures connection works even if Chrome doesn't trust the CA for QUIC
                        try:
                            from cryptography import x509
                            from cryptography.hazmat.primitives import hashes
                            from cryptography.hazmat.backends import default_backend
                            
                            c_content = c_file.read_bytes()
                            cert_obj = x509.load_pem_x509_certificate(c_content, default_backend())
                            app.state.webtransport_cert_hash = cert_obj.fingerprint(hashes.SHA256())
                            print(f"PyHTML: Calculated certificate hash for {c_file.name}")
                        except Exception as e:
                            print(f"PyHTML: Failed to calculate cert hash: {e}")
                        
                        break
                

                if not cert_path:
                    # Generate ephemeral self-signed certs
                    cert_path, key_path, fingerprint = _generate_cert()
                    app.state.webtransport_cert_hash = fingerprint

                config = Config()
                config.loglevel = "INFO"
                
                # Enable native WebTransport support
                config.enable_webtransport = True
                config.alpn_protocols = ["h3", "h2", "http/1.1"]

                # Bind dual-stack (IPv4 + IPv6) for localhost
                if host in ["127.0.0.1", "localhost"]:
                    config.bind = [f"127.0.0.1:{port}", f"[::1]:{port}"]
                    config.quic_bind = [f"127.0.0.1:{port}", f"[::1]:{port}"]
                else:
                    config.bind = [f"{host}:{port}"]
                    config.quic_bind = [f"{host}:{port}"]

                config.certfile = cert_path
                config.keyfile = key_path
                config.use_reloader = False

                display_host = "localhost" if host == "127.0.0.1" else host
                print(f"PyHTML: Running with Hypercorn (HTTP/3 + WebSocket) on https://{display_host}:{port}")
                tg.create_task(serve(app, config, shutdown_trigger=shutdown_event.wait))
            except Exception as e:
                print(f"PyHTML: Failed to start Hypercorn: {e}")
                import traceback
                traceback.print_exc()
                print("PyHTML: Falling back to Uvicorn (HTTP/2 + WebSocket only)")
                HAS_HTTP3 = False

        if not HAS_HTTP3:
            # Fallback to Uvicorn
            import uvicorn
            config = uvicorn.Config(
                app,
                host=host,
                port=port,
                reload=False,
                log_level="info"
            )
            server = uvicorn.Server(config)
            
            # Disable Uvicorn's signal handlers so we can manage it
            server.install_signal_handlers = lambda: None
            
            async def stop_uvicorn():
                await shutdown_event.wait()
                server.should_exit = True
            
            print(f"PyHTML: Running with Uvicorn on http://{host}:{port}")
            tg.create_task(server.serve())
            tg.create_task(stop_uvicorn())

        if reload:
            tg.create_task(watch_changes())
