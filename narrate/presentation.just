# Plan the explicitly selected private inputs; no media/provider/assembly command is executed.
set positional-arguments

plan manifest output:
    cd "{{justfile_directory()}}/.." && python3 -m narrate.presentation {{quote(manifest)}} {{quote(output)}}
