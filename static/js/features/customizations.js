// Busca grupos de customização de um produto
export async function fetchCustomizations(productId) {
  try {
    const res = await fetch(`/api/product/${productId}/customizations/`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.groups || [];
  } catch {
    return [];
  }
}

// Renderiza grupos dentro de um container
// applyToFilter: 'WHOLE' | 'HALF' | 'BOTH' | null (null = todos)
export function renderCustomizationGroups(container, groups, applyToFilter = null) {
  container.innerHTML = '';

  const filtered = applyToFilter
    ? groups.filter(g => g.apply_to === applyToFilter || g.apply_to === 'BOTH')
    : groups;

  if (!filtered.length) return;

  filtered.forEach(group => {
    const section = document.createElement('div');
    section.className = 'customization-group mb-4';
    section.dataset.groupId = group.id;
    section.dataset.minOptions = group.min_options;
    section.dataset.maxOptions = group.max_options;

    const isRequired = group.min_options > 0;
    const isMultiple = group.max_options > 1;

    section.innerHTML = `
      <div class="flex items-center justify-between mb-2">
        <h4 class="font-semibold text-gray-800 text-sm">${group.name}</h4>
        <span class="text-xs px-2 py-0.5 rounded-full ${isRequired ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-500'}">
          ${isRequired ? 'Obrigatório' : 'Opcional'}
        </span>
      </div>
      <div class="space-y-2" data-options-list></div>
    `;

    const optionsList = section.querySelector('[data-options-list]');

    group.options.forEach(opt => {
      const item = document.createElement('label');
      item.className = 'flex items-center gap-3 p-2 rounded-lg border border-gray-100 hover:border-primary/30 hover:bg-primary/5 cursor-pointer transition';

      const inputType = isMultiple ? 'checkbox' : 'radio';
      const inputName = `customization_group_${group.id}`;

      item.innerHTML = `
        <input type="${inputType}" name="${inputName}"
               value="${opt.id}"
               data-option-id="${opt.id}"
               data-option-name="${opt.name}"
               data-option-price="${opt.price}"
               data-group-id="${group.id}"
               data-group-name="${group.name}"
               class="accent-primary w-4 h-4 flex-shrink-0">
        ${opt.image ? `<img src="${opt.image}" class="w-10 h-10 rounded-lg object-cover flex-shrink-0" alt="${opt.name}">` : ''}
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-gray-700">${opt.name}</div>
          ${opt.description ? `<div class="text-xs text-gray-400 truncate">${opt.description}</div>` : ''}
        </div>
        <div class="text-sm font-semibold text-primary flex-shrink-0">
          ${parseFloat(opt.price) > 0 ? `+R$ ${parseFloat(opt.price).toFixed(2).replace('.', ',')}` : 'Grátis'}
        </div>
      `;

      optionsList.appendChild(item);
    });

    container.appendChild(section);
  });
}

// Coleta as opções selecionadas de um container
export function collectSelectedOptions(container) {
  const selected = [];
  container.querySelectorAll('input[type="radio"]:checked, input[type="checkbox"]:checked').forEach(input => {
    selected.push({
      group_id: input.dataset.groupId,
      group_name: input.dataset.groupName,
      option_id: input.dataset.optionId,
      option_name: input.dataset.optionName,
      price: input.dataset.optionPrice,
    });
  });
  return selected;
}

export function validateRequiredGroups(container, groups) {
  for (const group of groups) {
    if (group.min_options === 0) continue;
    const checked = container.querySelectorAll(`input[name="customization_group_${group.id}"]:checked`);
    if (checked.length < group.min_options) return group.name;
  }
  return null;
}