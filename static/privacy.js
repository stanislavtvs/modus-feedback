(() => {
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  function review(preview){
    return new Promise(resolve=>{
      const dialog=node('dialog');dialog.className='privacy-dialog';dialog.setAttribute('aria-labelledby','privacy-heading');
      const heading=node('h2','Проверьте текст перед отправкой');heading.id='privacy-heading';
      const destination=node('p',`Получатель: ${preview.destination} · ${preview.model}`);
      const explanation=node('p','Сейчас данные остаются в приложении. В ИИ они уйдут только после вашего подтверждения. Исходное обращение не изменится.');
      const warning=node('p','Поиск по шаблонам может пропустить имена, адреса и другие личные данные. Проверьте весь текст самостоятельно.');warning.className='hint';
      const findings=node('p',preview.findings.length?`Возможные данные: ${preview.findings.map(item=>`${item.label}: ${item.count}`).join('; ')}.`:'По известным шаблонам данные не найдены. Это не гарантия их отсутствия.');
      const label=node('label');label.className='privacy-toggle';const checkbox=node('input');checkbox.type='checkbox';checkbox.checked=true;
      label.append(checkbox,document.createTextNode(' Скрыть найденные данные перед отправкой'));
      const pre=node('pre');pre.className='privacy-preview';pre.tabIndex=0;pre.setAttribute('aria-label','Данные, которые будут отправлены');
      const update=()=>{
        const text=JSON.stringify(checkbox.checked?preview.masked:preview.original,null,2);pre.replaceChildren();
        const pattern=checkbox.checked?/\[(?:EMAIL|ТЕЛЕФОН|ИДЕНТИФИКАТОР|ПАСПОРТ) СКРЫТ\]/g:/[\w.+-]+@[\w-]+(?:\.[\w-]+)+|(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}|\b\d{12}\b|\b\d{2}\s?\d{2}\s+\d{6}\b/g;
        let end=0;for(const match of text.matchAll(pattern)){pre.append(document.createTextNode(text.slice(end,match.index)),node('mark',match[0]));end=match.index+match[0].length;}pre.append(document.createTextNode(text.slice(end)));
      };checkbox.addEventListener('change',update);update();
      const detail=node('p','Показан пакет данных для модели. Сервер также добавит служебные инструкции и схему JSON. Поля профиля и вложения не отправляются.');detail.className='hint';
      const actions=node('div');actions.className='actions';const cancel=node('button','Отмена');cancel.type='button';cancel.className='secondary';const confirm=node('button','Подтверждаю отправку в ИИ');confirm.type='button';confirm.className='primary';actions.append(cancel,confirm);
      let completed=false;const finish=value=>{if(completed)return;completed=true;dialog.close();dialog.remove();resolve(value);};
      cancel.addEventListener('click',()=>finish(null));confirm.addEventListener('click',()=>finish(checkbox.checked));dialog.addEventListener('cancel',event=>{event.preventDefault();finish(null);});
      dialog.append(heading,destination,explanation,findings,label,pre,warning,detail,actions);document.body.append(dialog);dialog.showModal();cancel.focus();
    });
  }
  window.reviewedAI=async(url,body={},onConfirmed=()=>{})=>{
    const csrf=document.querySelector('[name=csrfmiddlewaretoken]')?.value||'';
    const send=async data=>{
      const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),95000);
      try{
        const response=await fetch(url,{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify(data)});
        if(response.redirected||response.status===403)throw new Error('Сессия истекла или доступ изменился. Обновите страницу.');
        let payload;try{payload=await response.json();}catch{throw new Error('Сервис не смог вернуть ответ.');}
        return {response,payload};
      }finally{clearTimeout(timeout);}
    };
    let {response,payload}=await send(body);
    if(payload.preview){
      const mask=await review(payload.preview);
      if(mask===null){const error=new Error('Отправка отменена. Данные не переданы в ИИ.');error.name='ReviewCancelled';throw error;}
      onConfirmed();
      ({response,payload}=await send({...body,privacy_token:payload.privacy_token,hide_sensitive:mask}));
    }
    if(!response.ok)throw new Error(payload.error||'Не удалось выполнить запрос.');
    return payload;
  };
})();
