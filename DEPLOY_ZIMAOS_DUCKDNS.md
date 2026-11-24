# Anleitung: Portainer auf ZimaOS & Einbindung in den DuckDNS-Service des VPS

Diese Schritt-für-Schritt-Anleitung beschreibt:
1. Das Deployment des Stacks in **Portainer auf ZimaOS**.
2. Die Anbindung deines **VPS mit DuckDNS** (IP-Updater, Tunnel/VPN zu ZimaOS und HTTPS Reverse Proxy mit korrektem Streaming für SSE & Chunked Uploads).

---

## Teil 1: Stack in Portainer auf ZimaOS deployen

### 1.1 Voraussetzungen auf ZimaOS
- Portainer ist auf ZimaOS installiert und erreichbar.
- Die Docker-Images werden über GitHub Actions automatisch gebaut und auf `ghcr.io/smb04/file-converter-*` bereitgestellt (siehe `.github/workflows/build-images.yml`).
  - *Hinweis zu privaten Packages:* Falls deine GHCR-Images auf GitHub als „Private“ stehen, entweder in den GitHub Package Settings auf **Public** stellen oder in Portainer unter **Registries -> Add registry** einen GitHub PAT (`read:packages`) hinterlegen.

### 1.2 Stack in Portainer anlegen
1. Öffne **Portainer -> Stacks -> + Add stack**.
2. Name des Stacks: `file-converter`.
3. Wähle **Repository** (URL: `https://github.com/Smb04/file-converter`, Branch: `refs/heads/main`, Compose path: `docker-compose.yml`) **oder** füge den Inhalt von `docker-compose.yml` direkt in den Web-Editor ein.
4. Lege im Abschnitt **Environment variables** folgende Variablen an (siehe `.env.example`):

| Variable | Empfohlener Wert (ZimaOS 8–16 GB RAM) | Hinweis |
| :--- | :--- | :--- |
| `REGISTRY_PREFIX` | `ghcr.io/smb04/file-converter` | Basis-Pfad der Images |
| `IMAGE_TAG` | `latest` | Oder spezifischer `sha-...` Tag |
| `APP_PORT` | `8095` | Lokaler Host-Port auf ZimaOS |
| `BUFFER_TMPFS_SIZE` | `2G` (bei 16 GB RAM auch `4G`) | RAM-Disk Größe (keine SSD-Abnutzung) |
| `JOB_TTL_SECONDS` | `1200` | Automatische Löschung nach 20 Minuten |
| `MAX_FILE_BYTES` | `524288000` | Max. 500 MB pro Einzeldatei |
| `MAX_BATCH_BYTES` | `1073741824` | Max. 1 GB pro Batch |
| `MEDIA_CONCURRENCY` | `2` | Optimal für Intel N100 / 4-Core |
| `DOCS_CONCURRENCY` | `2` | Parallele LibreOffice-Jobs |
| `ENABLE_HW_ACCEL` | `false` (oder `true` mit iGPU) | Siehe Abschnitt 1.3 |

5. Klicke auf **Deploy the stack**.
6. Prüfe nach ca. 20 Sekunden in Portainer unter **Containers**, ob `gateway`, `api`, `redis`, `worker-media` und `worker-docs` auf `healthy` / `running` stehen.
7. Erster lokaler Funktionstest auf ZimaOS:
   ```bash
   curl http://127.0.0.1:8095/api/v1/health
   ```
   Erwartete Antwort: `{"status":"ok","redis":true,...}`.

### 1.3 Optional: Intel Arc GPU & Intel QuickSync / VAAPI auf ZimaOS aktivieren
Besitzt dein ZimaOS-Server eine dedizierte **Intel Arc GPU** (unterstützt H.264, H.265, VP9 **und AV1** in Hardware) oder eine Intel-CPU-iGPU:
1. Auf ZimaOS per SSH prüfen, welches Render-Device zur Intel Arc gehört (wichtig falls zusätzlich eine CPU-iGPU aktiv ist!):
   ```bash
   ls -la /dev/dri/by-path
   stat -c '%g' /dev/dri/renderD128
   ```
   *(Liegt die Intel Arc auf `renderD129` statt `renderD128`, setze unten entsprechend `VAAPI_DEVICE=/dev/dri/renderD129` und ermittle auch deren GID.)*
2. In `docker-compose.yml` beim Service `worker-media` den auskommentierten `devices:`- und `group_add:`-Block einkommentieren.
3. In Portainer folgende Environment-Variablen setzen und den Stack neu deployen:
   - `ENABLE_HW_ACCEL=true`
   - `VAAPI_DEVICE=/dev/dri/renderD128` *(oder `renderD129`)*
   - `RENDER_GID=<ermittelte-GID>` *(z. B. `109`)*
4. Funktionstest direkt im laufenden Container ausführen:
   ```bash
   docker exec -it file-converter-worker-media-1 vainfo --display drm --device /dev/dri/renderD128
   ```
   *(Die Ausgabe sollte Profile für `H264`, `HEVC`, `VP9` und bei Intel Arc auch `AV1` auflisten. Schlägt bei einem exotischen Video ein Hardware-Durchlauf fehl, schaltet der Worker automatisch auf CPU-Encoding zurück.)*

### 1.4 Optional: Große Videos (> 2 GB) statt RAM auf Scratch-Ordner puffern
Beachte, dass während einer Video-Konvertierung Eingabe- und Ausgabedatei gleichzeitig im Buffer liegen. Bei `BUFFER_TMPFS_SIZE=2G` sind Videodateien bis ca. 800 MB unkritisch. Falls regelmäßig mehrstündige 4K-Videos konvertiert werden und dein ZimaOS-RAM begrenzt ist, kommentiere in `docker-compose.yml` unter `volumes:` Variante A (`tmpfs`) aus und aktiviere Variante B mit einem dedizierten Scratch-Ordner (z. B. `/DATA/AppData/converter-scratch`).

---

## Teil 2: Einbindung in den DuckDNS-Service des VPS

Das typische Setup besteht aus zwei Teilen:
1. **DuckDNS** hält eine Subdomain (z. B. `dein-converter.duckdns.org`) automatisch auf der öffentlichen IP-Adresse deines VPS.
2. Dein **VPS** nimmt HTTPS-Anfragen entgegen und leitet sie sicher über einen Tunnel (WireGuard / Tailscale / Reverse-SSH) an ZimaOS Port `8095` weiter.

> **Wichtige Sicherheitsregel:** Öffne Port `8095` auf ZimaOS **nicht** unverschlüsselt direkt ins Internet! Verbinde VPS und ZimaOS über **WireGuard**, **Tailscale** oder einen **SSH-Reverse-Tunnel**.

### Schritt 2.1 DuckDNS-Subdomain einrichten
1. Melde dich auf [https://www.duckdns.org](https://www.duckdns.org) an.
2. Lege eine Subdomain an, z. B. `myconverter` (ergibt `myconverter.duckdns.org`).
3. Notiere dir deinen persönlichen **DuckDNS-Token** und trage initial die öffentliche IPv4 (und falls genutzt IPv6) deines VPS ein.

### Schritt 2.2 DuckDNS-Updater auf dem VPS einrichten
Falls DuckDNS auf deinem VPS noch nicht automatisch aktualisiert wird, wähle eine der beiden Methoden:

**Methode A: Leichtgewichtiger Cronjob auf dem VPS (empfohlen)**
```bash
mkdir -p ~/duckdns
cat <<'EOF' > ~/duckdns/duck.sh
#!/usr/bin/env bash
echo url="https://www.duckdns.org/update?domains=DEINE_SUBDOMAIN&token=DEIN_DUCKDNS_TOKEN&ip=" | curl -k -s -o ~/duckdns/duck.log -K -
EOF
chmod 700 ~/duckdns/duck.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
~/duckdns/duck.sh && cat ~/duckdns/duck.log
```
*(Ausgabe muss `OK` sein.)*

**Methode B: Falls dein VPS DuckDNS als Docker-Container betreibt**
```yaml
services:
  duckdns:
    image: lscr.io/linuxserver/duckdns:latest
    container_name: duckdns
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Berlin
      - SUBDOMAINS=DEINE_SUBDOMAIN
      - TOKEN=DEIN_DUCKDNS_TOKEN
    restart: unless-stopped
```

### Schritt 2.3 Tunnel zwischen VPS und ZimaOS herstellen
- **Variante 1 (Empfohlen – WireGuard / Tailscale):**
  Beide Maschinen (VPS + ZimaOS) befinden sich im selben Mesh-/VPN-Netz. Dein ZimaOS ist vom VPS aus direkt unter seiner VPN-IP erreichbar (z. B. `100.64.0.12:8095` bei Tailscale oder `10.8.0.2:8095` bei WireGuard).
- **Variante 2 (Falls kein VPN installiert ist – SSH-Reverse-Tunnel von ZimaOS zum VPS):**
  Auf ZimaOS als Systemd-Service oder `autossh` starten:
  ```bash
  ssh -N -R 127.0.0.1:8095:127.0.0.1:8095 user@DEIN_VPS
  ```
  Dann erreicht der Reverse Proxy auf dem VPS den Konverter unter `http://127.0.0.1:8095`.

### Schritt 2.4 Reverse Proxy auf dem VPS konfigurieren (HTTPS + SSE + Chunked Uploads)

Ersetze `ZIMAOS_TARGET` durch deine Tunnel-Adresse (z. B. `100.64.0.12:8095` oder `127.0.0.1:8095`) und `DEINE_SUBDOMAIN.duckdns.org` durch deine echte DuckDNS-Domain.

#### Option A: Nginx + Certbot auf dem VPS
Erstelle `/etc/nginx/sites-available/converter.conf`:

```nginx
server {
    listen 80;
    server_name DEINE_SUBDOMAIN.duckdns.org;

    # Chunks sind <= 10 MB; 25M bietet sauberen Puffer
    client_max_body_size 25M;

    # Registrierung & Kontoverwaltung ueber DuckDNS bereits am VPS-Edge blockieren
    location ~ ^/api/v1/auth/(register|users|password) {
        return 403;
    }

    # SSE-Live-Fortschritt: Pufferung zwingend deaktivieren
    location ~ ^/api/v1/batches/[^/]+/events$ {
        proxy_pass http://ZIMAOS_TARGET;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-External-Proxy "1";
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        proxy_pass http://ZIMAOS_TARGET;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-External-Proxy "1";
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_read_timeout 600s;
    }
}
```

Aktivieren und HTTPS-Zertifikat via Let's Encrypt ausstellen:
```bash
sudo ln -s /etc/nginx/sites-available/converter.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d DEINE_SUBDOMAIN.duckdns.org
```

#### Option B: Caddy auf dem VPS (automatisches HTTPS ab Werk)
In `/etc/caddy/Caddyfile`:

```caddyfile
DEINE_SUBDOMAIN.duckdns.org {
    request_body {
        max_size 25MB
    }

    @blocked_admin path /api/v1/auth/register* /api/v1/auth/users* /api/v1/auth/password*
    respond @blocked_admin 403

    reverse_proxy ZIMAOS_TARGET {
        flush_interval -1
        header_up X-External-Proxy "1"
        transport http {
            read_timeout 3600s
            write_timeout 600s
        }
    }
}
```
Danach `sudo systemctl reload caddy`.

#### Option C: Nginx Proxy Manager (NPM) auf dem VPS
1. **Proxy Hosts -> Add Proxy Host**:
   - **Domain Names:** `DEINE_SUBDOMAIN.duckdns.org`
   - **Scheme:** `http`, **Forward Hostname/IP:** `ZIMAOS_TARGET` (IP ohne Port), **Forward Port:** `8095`
   - **Block Common Exploits:** Aktiviert
   - **Websockets Support:** Aktiviert
2. Tab **SSL**: *Request a new SSL Certificate*, **Force SSL** und **HTTP/2 Support** aktivieren.
3. Tab **Advanced -> Custom Nginx Configuration** einfügen:
   ```nginx
   client_max_body_size 25M;
   proxy_buffering off;
   proxy_request_buffering off;
   proxy_read_timeout 3600s;
   proxy_set_header X-External-Proxy "1";

   location ~ ^/api/v1/auth/(register|users|password) {
       return 403;
   }
   ```

### Schritt 2.5 Authentifizierung & Vaultwarden-Ersteinrichtung
Der Konverter ist vollständig durch eine Anmeldung geschützt:

1. **Ersteinrichtung nur im lokalen LAN:**
   Öffne direkt nach dem ersten Stack-Start **nicht** die DuckDNS-Domain, sondern die lokale ZimaOS-IP:
   ```text
   http://<DEINE-ZIMAOS-LAN-IP>:8095
   ```
   Dort erscheint automatisch das Formular **„Erstes Konto im lokalen LAN anlegen“**.
2. **In Vaultwarden speichern:**
   Lege Benutzername und Passwort (mind. 10 Zeichen) an. Dein Browser / deine Vaultwarden-Extension erkennt das Standard-`<form>` automatisch (`username` + `new-password`) und bietet das Speichern an. Ergänze in Vaultwarden als zweite URI deine DuckDNS-URL (`https://DEINE_SUBDOMAIN.duckdns.org`), damit Vaultwarden auf beiden Adressen automatisch ausfüllt.
3. **Nutzung über DuckDNS:**
   Auf `https://DEINE_SUBDOMAIN.duckdns.org` ist ausschließlich die **Anmeldung** (optional *30 Tage angemeldet bleiben* über ein signiertes `HttpOnly`-Cookie) möglich. Registrierung, Passwortänderung und Kontoverwaltung werden auf 4 Ebenen blockiert (VPS-Edge, Proxy-Marker-Prüfung, Host-Header-Prüfung und `LOCAL_ADMIN_CIDRS`).
4. **Optionaler Tipp für WireGuard/Tailscale:**
   Falls dein Heim-Subnetz z. B. `192.168.178.0/24` ist, kannst du in Portainer optional `LOCAL_ADMIN_CIDRS=192.168.178.0/24,127.0.0.0/8` setzen — dann werden Admin-Aktionen selbst im LAN ausschließlich aus deinem konkreten Heimnetz-Subnetz akzeptiert.

---

## Teil 3: Funktionsprüfung nach Inbetriebnahme

1. Rufe `https://DEINE_SUBDOMAIN.duckdns.org` im Browser auf.
2. Ziehe mehrere Dateien (z. B. ein Bild und ein PDF) per Drag & Drop ins Fenster.
3. Prüfe, dass der Upload- und Konvertierungs-Fortschritt flüssig in Echtzeit hochzählt (SSE funktioniert).
4. Klicke auf **„Alle Dateien jetzt loeschen“** und verifiziere auf ZimaOS im Container `api`, dass `/buffer/batches/` sofort leer ist:
   ```bash
   docker exec -it file-converter-api-1 ls -la /buffer/batches
   ```
