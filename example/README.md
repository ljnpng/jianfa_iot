# Home Assistant Docker Example

This directory contains a Docker Compose setup for running Home Assistant with the C&D IoT custom integration for testing purposes.

## Quick Start

1. **Start Home Assistant:**
   ```bash
   cd example
   docker-compose up -d
   ```

2. **Access Home Assistant:**
   - Open http://localhost:8123 in your browser
   - First time: Create an admin account

3. **Add the C&D IoT Integration:**
   - Settings → Devices & Services → Add Integration
   - Search for "C&D IoT"
   - Follow the SMS verification flow

4. **View Logs:**
   ```bash
   docker-compose logs -f homeassistant
   ```

5. **Stop Home Assistant:**
   ```bash
   docker-compose down
   ```

## Project Structure

```
example/
├── docker-compose.yml      # Docker Compose configuration
└── ha_data/                # Home Assistant configuration
    ├── configuration.yaml   # Main HA configuration
    ├── automations.yaml     # Automation definitions
    ├── scripts.yaml         # Script definitions
    ├── scenes.yaml          # Scene definitions
    ├── .gitignore          # Excludes runtime data
    └── .storage/           # HA storage directory
```

## Volume Mounts

- **`./ha_data:/config`** - Home Assistant configuration data
- **`../custom_components/jianfa_iot:/config/custom_components/jianfa_iot:ro`** - Custom integration source code

The custom integration is mounted read-only, so you can modify the source code in the parent directory and restart the container to see changes.

## Restarting After Code Changes

After modifying the integration source code:

```bash
docker-compose restart homeassistant
```

## Troubleshooting

**Integration not showing up:**
```bash
# Check logs for errors
docker-compose logs homeassistant | grep jianfa_iot

# Verify files are mounted
docker-compose exec homeassistant ls -la /config/custom_components/jianfa_iot/
```

**Permission issues:**
```bash
# Fix permissions if needed
sudo chown -R 8123:8123 ha_data/
```

**Reset everything:**
```bash
# Stop and remove containers
docker-compose down

# Remove HA data (optional - requires reconfiguration)
rm -rf ha_data/.HA_VERSION ha_data/home-assistant_v2.db*

# Restart
docker-compose up -d
```

## Configuration

To modify Home Assistant settings, edit `ha_data/configuration.yaml` and restart:

```bash
docker-compose restart homeassistant
```

## Default Credentials

First-time setup requires creating an admin account through the web UI.
