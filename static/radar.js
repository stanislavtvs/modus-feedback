document.addEventListener('DOMContentLoaded',()=>{
  const form=document.getElementById('radar-form');if(!form)return;
  form.addEventListener('submit',async event=>{
    event.preventDefault();const button=form.querySelector('button');const status=document.getElementById('radar-status');
    button.disabled=true;status.textContent='Ищем общие темы. Обычно это занимает до минуты…';form.setAttribute('aria-busy','true');
    try{const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{'Accept':'application/json'}});const data=await response.json();if(!response.ok)throw new Error(data.error||'Не удалось выполнить анализ.');status.textContent=data.message;if(data.created)window.location.reload();}
    catch(error){status.textContent=error.message||'Не удалось связаться с сервером.';}
    finally{button.disabled=false;form.removeAttribute('aria-busy');}
  });
});
