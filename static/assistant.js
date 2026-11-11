(() => {
    const el = (tag, text, className) => {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (className) node.className = className;
        return node;
    };
    const input = name => document.getElementById(`id_${name}`);
    const draftState = () => Object.fromEntries(['title','description','suggestion','category','kind','priority'].map(name => [name, input(name)?.value || '']));
    for (const panel of document.querySelectorAll('[data-ai-assistant]')) {
        const button = panel.querySelector('.ai-run');
        const status = panel.querySelector('.ai-status');
        const result = panel.querySelector('.ai-result');
        const isDraft = panel.dataset.aiMode === 'draft';
        const paragraph = (heading, value) => {
            if (!value) return;
            result.append(el('h3', heading), el('p', value));
        };
        const list = (heading, values) => {
            if (!Array.isArray(values) || !values.length) return;
            const ul = el('ul');
            for (const value of values) ul.append(el('li', value));
            result.append(el('h3', heading), ul);
        };
        const announce = (text, error = false) => {
            status.textContent = text;
            status.classList.toggle('ai-error', error);
        };
        button.addEventListener('click', async () => {
            if (button.disabled) return;
            const snapshot = isDraft ? draftState() : null;
            if (isDraft && snapshot.description.trim().length < 15) {
                announce('Сначала опишите ситуацию хотя бы в одном предложении (от 15 символов).', true);
                input('description')?.focus();
                return;
            }
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            result.hidden = true;
            result.replaceChildren();
            announce('Сначала проверьте пакет данных. После подтверждения Gemma подготовит предложение.');
            try {
                const payload = await window.reviewedAI(panel.dataset.aiUrl,snapshot ? {title:snapshot.title,description:snapshot.description,suggestion:snapshot.suggestion} : {},()=>announce('Gemma готовит предложение. Это может занять до полутора минут.'));
                const data = payload.result;
                if (isDraft) {
                    paragraph('Заголовок', data.title);
                    paragraph('Описание', data.description);
                    const kinds = {problem:'Проблема',idea:'Предложение',praise:'Положительный отзыв'};
                    const priorities = {low:'Низкий',medium:'Средний',high:'Высокий'};
                    paragraph('Предлагаемая классификация', `${data.category_name || 'Категорию выберите сами'} · ${kinds[data.kind]} · Приоритет: ${priorities[data.priority]}`);
                    paragraph('Почему так', data.reason);
                    list('Что можно уточнить', data.questions);
                    const apply = el('button', 'Применить к форме', 'primary ai-apply');
                    apply.type = 'button';
                    apply.addEventListener('click', () => {
                        if (JSON.stringify(draftState()) !== JSON.stringify(snapshot)) {
                            announce('Вы изменили форму после запроса. Запросите новое предложение, чтобы сохранить ваши правки.', true);
                            apply.disabled = true;
                            return;
                        }
                        for (const key of ['title','description','kind','priority']) input(key).value = data[key];
                        if (data.category_id !== null) input('category').value = String(data.category_id);
                        for (const key of ['title','description','kind','priority','category']) input(key).dispatchEvent(new Event('change', {bubbles:true}));
                        apply.disabled = true;
                        announce('Предложение добавлено в форму. Проверьте текст перед отправкой.');
                        input('title').focus();
                    });
                    result.append(apply);
                } else {
                    paragraph('Краткая суть', data.summary);
                    paragraph('Простыми словами', data.plain_language);
                    list('Что стоит уточнить', data.questions);
                    list('Возможные следующие шаги', data.next_steps);
                    const resolution = input('resolution');
                    if (data.reply_draft && resolution) {
                        paragraph('Черновик ответа автору', data.reply_draft);
                        const apply = el('button', 'Добавить в поле решения', 'ai-apply');
                        apply.type = 'button';
                        apply.addEventListener('click', () => {
                            resolution.value = [resolution.value.trim(), data.reply_draft].filter(Boolean).join('\n\n');
                            resolution.dispatchEvent(new Event('input', {bubbles:true}));
                            resolution.focus();
                            apply.disabled = true;
                            announce('Черновик добавлен в поле решения. Проверьте его и сохраните изменения самостоятельно.');
                        });
                        result.append(apply);
                    }
                }
                result.hidden = false;
                announce('Предложение готово. Проверьте точность формулировок.');
                result.focus();
            } catch (error) {
                announce(error.name === 'AbortError' ? 'Ожидание ответа истекло. Текст не изменён. Повторите попытку позже.' : error.message, error.name !== 'ReviewCancelled');
            } finally {
                button.disabled = false;
                button.removeAttribute('aria-busy');
                if(result.hidden) button.focus();
            }
        });
    }
})();
