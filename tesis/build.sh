#!/bin/bash
# Compila la tesis y abre el PDF resultante.
# Uso: ./build.sh

cd "$(dirname "$0")" || exit

echo "Compilando..."
latexmk -pdf -interaction=nonstopmode main.tex

if [ $? -eq 0 ]; then
    echo "Compilación exitosa."
    open main.pdf
else
    echo "Error de compilación. Revisá el log: main.log"
    exit 1
fi
