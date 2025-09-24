#!/bin/bash

# This is a simple build script for packaging the Lambda function.
# You might need to customize it based on your deployment strategy.

echo "Zipping Lambda deployment package..."
zip -r deployment_package.zip src/ requirements.txt config.json

echo "Done."
