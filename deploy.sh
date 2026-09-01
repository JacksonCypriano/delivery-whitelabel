#!/usr/bin/env bash

# Publica homolog em main no Git. Não executa deploy de containers.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REMOTE="origin"
SOURCE_BRANCH="homolog"
TARGET_BRANCH="main"
RETURN_TO_SOURCE=false
MERGE_STARTED=false
PUSH_SUCCEEDED=false

fail() {
    echo "❌ $*" >&2
    exit 1
}

cleanup() {
    result=$?
    trap - EXIT
    set +e

    if [[ "$MERGE_STARTED" == true ]] && git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
        echo "▶ Abortando o merge que não foi concluído..."
        if ! git merge --abort; then
            echo "❌ Não foi possível abortar o merge. Resolva o estado do Git antes de continuar." >&2
            exit 1
        fi
    fi

    if [[ "$RETURN_TO_SOURCE" == true ]]; then
        echo "▶ Voltando para $SOURCE_BRANCH..."
        if ! git switch "$SOURCE_BRANCH"; then
            echo "❌ Não foi possível voltar para $SOURCE_BRANCH. Confira git status." >&2
            exit 1
        fi
    fi

    if [[ "$result" -ne 0 ]]; then
        echo "❌ Publicação interrompida. Confira o erro acima." >&2
        if [[ "$PUSH_SUCCEEDED" == false ]]; then
            echo "Um merge já concluído pode permanecer na main local. Confira git status antes de repetir." >&2
        fi
    elif [[ "$PUSH_SUCCEEDED" == true ]]; then
        echo "✅ main publicada em $REMOTE. Você está na branch $SOURCE_BRANCH."
    fi
    exit "$result"
}

command -v git >/dev/null 2>&1 || fail "Git não foi encontrado."
git rev-parse --show-toplevel >/dev/null 2>&1 || fail "Salve este script dentro do repositório."
cd "$(git rev-parse --show-toplevel)"

[[ -z "$(git status --porcelain)" ]] || fail "Há arquivos modificados ou não rastreados. Faça commit ou guarde as alterações antes de executar."

for operation in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
    [[ ! -e "$(git rev-parse --git-path "$operation")" ]] || fail "Existe uma operação Git pendente ($operation). Conclua ou aborte antes de executar."
done

git remote get-url "$REMOTE" >/dev/null 2>&1 || fail "Remote $REMOTE não encontrado."
git show-ref --verify --quiet "refs/heads/$SOURCE_BRANCH" || fail "Branch local $SOURCE_BRANCH não encontrada."

# A partir daqui, tentamos retornar à homolog tanto no sucesso como na falha.
trap cleanup EXIT

git switch "$SOURCE_BRANCH"
RETURN_TO_SOURCE=true

echo "▶ Atualizando as referências de $REMOTE..."
git fetch "$REMOTE"
git show-ref --verify --quiet "refs/remotes/$REMOTE/$SOURCE_BRANCH" || fail "Branch remota $REMOTE/$SOURCE_BRANCH não encontrada."
git show-ref --verify --quiet "refs/remotes/$REMOTE/$TARGET_BRANCH" || fail "Branch remota $REMOTE/$TARGET_BRANCH não encontrada."

echo "▶ Sincronizando $SOURCE_BRANCH sem criar merge automático..."
git merge --ff-only "$REMOTE/$SOURCE_BRANCH"
SOURCE_COMMIT="$(git rev-parse HEAD)"

echo "▶ Mudando para $TARGET_BRANCH..."
if git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
    git switch "$TARGET_BRANCH"
else
    git switch --track -c "$TARGET_BRANCH" "$REMOTE/$TARGET_BRANCH"
fi

echo "▶ Sincronizando $TARGET_BRANCH com $REMOTE/$TARGET_BRANCH..."
git merge --ff-only "$REMOTE/$TARGET_BRANCH"

echo "▶ Fazendo merge de $SOURCE_BRANCH em $TARGET_BRANCH..."
MERGE_STARTED=true
git merge --no-edit "$SOURCE_COMMIT"
MERGE_STARTED=false

echo "▶ Publicando $TARGET_BRANCH..."
git push "$REMOTE" "refs/heads/$TARGET_BRANCH:refs/heads/$TARGET_BRANCH"
PUSH_SUCCEEDED=true
