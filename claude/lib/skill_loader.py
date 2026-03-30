#!/usr/bin/env python3
"""Cargador de skills para agentes.

Las skills son markdown files que contienen expertise / conocimiento del dominio
que complementan las órdenes del agente (.md). Se inyectan en el system prompt
después del contenido del .md del agente.
"""

from __future__ import annotations

import re
from pathlib import Path


def parse_agent_metadata(agent_md_path: Path) -> dict:
    """Extrae el frontmatter YAML del .md del agente.

    Soporta:
        model: claude-sonnet-4-6
        skills:
          - json-navigator
          - otra-skill

    Devuelve:
        dict: {"model": "claude-sonnet-4-6", "skills": ["json-navigator"], ...}
    """
    try:
        content = agent_md_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    # Extraer frontmatter YAML (entre --- ... ---)
    if not content.startswith("---"):
        return {}

    end = content.find("---", 3)
    if end == -1:
        return {}

    frontmatter = content[3:end].strip()
    metadata = {}
    current_list = None
    current_key = None

    for line in frontmatter.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Detectar array YAML: "  - item"
        if line.startswith("  - "):
            if current_list is not None:
                item = line[4:].strip()
                current_list.append(item)
            continue

        # Parsear: clave: valor
        if ":" in line:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()

            current_key = key

            # Convertir arrays en una línea: skills: [json-navigator, map-navigator]
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip() for x in val[1:-1].split(",")]
                metadata[key] = items
                current_list = None
            # Preparar array multi-línea
            elif val == "":
                current_list = []
                metadata[key] = current_list
            else:
                metadata[key] = val
                current_list = None

    return metadata


def load_skill(skill_name: str, skill_dir: Path) -> str | None:
    """Carga una skill en markdown.

    Args:
        skill_name: nombre de la skill (ej: "json-navigator")
        skill_dir: directorio donde buscar skills (ej: claude/skills/)

    Returns:
        Contenido del skill .md, o None si no existe
    """
    skill_path = skill_dir / f"{skill_name}.md"
    try:
        return skill_path.read_text(encoding="utf-8")
    except OSError:
        return None


def build_system_prompt(
    agent_md_path: Path,
    skill_dir: Path = None,
) -> str:
    """Construye el system prompt completo para un agente.

    Estructura:
    1. Contenido del agent.md (sin frontmatter)
    2. Si frontmatter tiene "skills": inyecta contenido de cada skill

    Args:
        agent_md_path: ruta a agent.md (ej: claude/agents/reader.md)
        skill_dir: ruta al directorio de skills (default: agent_dir/../skills/)

    Returns:
        String con system prompt listo para pasar a claude CLI
    """
    if not agent_md_path.exists():
        return ""

    # Ruta por defecto
    if skill_dir is None:
        skill_dir = agent_md_path.parent.parent / "skills"

    content = agent_md_path.read_text(encoding="utf-8")

    # Remover frontmatter YAML
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            # Parsear metadata antes de removerla
            metadata = parse_agent_metadata(agent_md_path)
            content = content[end + 3:].lstrip("\n")
        else:
            metadata = {}
    else:
        metadata = {}

    # Inyectar skills si están declaradas en metadata
    skills = metadata.get("skills", [])
    if skills:
        for skill_name in skills:
            skill_content = load_skill(skill_name, skill_dir)
            if skill_content:
                # Quitar frontmatter si existe
                if skill_content.startswith("---"):
                    end = skill_content.find("---", 3)
                    if end != -1:
                        skill_content = skill_content[end + 3:].lstrip("\n")

                # Agregar como sección
                content += f"\n\n---\n\n{skill_content}"

    return content


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python skill_loader.py <agent.md>")
        sys.exit(1)

    agent_path = Path(sys.argv[1])
    prompt = build_system_prompt(agent_path)
    print(prompt)
