#!/bin/bash

DIR=$(dirname $0)

# First time setup
if [[ $1 == "fresh" ]] || [[ ! -e "$DIR/external/config/core-config.yaml" ]]; then

    # Start with a new config file from the repository
    if [[ $1 == "fresh" ]]; then
        read -p "Overwrite old config file? [y/N] " OVERWRITE
        OVERWRITE=${OVERWRITE:-n}
        if [[ $OVERWRITE =~ ^[Nn]$ ]]; then
            echo "Skipping config file."
        fi
    else
        OVERWRITE="y"
    fi

    mkdir -p "$DIR/external/config"

    if [[ $OVERWRITE =~ ^[Yy]$ ]]; then
        echo "Downloading config file..."
        wget -O "$DIR/external/config/core-config.yaml" \
            "https://raw.githubusercontent.com/jkchen2/JshBot/master/config/core-config.yaml"
        if [[ $? != 0 ]]; then
            echo "Failed to download the config file."
            exit 1
        fi
    fi

    echo "Downloading Docker Compose file..."
    wget -O "$DIR/docker-compose.yaml" \
        "https://raw.githubusercontent.com/jkchen2/JshBot/master/scripts/docker-compose.yaml"
    if [[ $? != 0 ]]; then
        echo "Failed to download the Docker Compose file."
        exit 1
    fi

    # Detect editors
    if [[ -e /usr/bin/gedit ]]; then
        EDITOR="gedit -w"
    elif [[ -e /usr/bin/nano ]]; then
        EDITOR="nano"
    else
        EDITOR="vi"
    fi
    read -p "Choose editor to edit core-config.yaml [default: $EDITOR] " RESPONSE
    EDITOR=${RESPONSE:-$EDITOR}
    $EDITOR "$DIR/external/config/core-config.yaml"
    echo "Config setup complete!"
fi

# Start the bot
echo "Starting the bot..."
if docker info > /dev/null 2>&1; then
    docker-compose -f "$DIR/docker-compose.yaml" up
else
    echo "User $(whoami) does not seem to have access to the Docker daemon. Trying in root..."
    sudo docker-compose -f "$DIR/docker-compose.yaml" up
fi
echo "Exited."
