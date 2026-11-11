document.addEventListener('DOMContentLoaded',()=>{
  const form=document.getElementById('radar-form');if(!form)return;
  form.addEventListener('submit',async event=>{
    event.preventDefault();const button=form.querySelector('button');const status=document.getElementById('radar-status');
    button.disabled=true;status.textContent='Проверьте данные перед анализом. После подтверждения ИИ начнёт искать темы…';form.setAttribute('aria-busy','true');
    try{const data=await window.reviewedAI(form.action,{},()=>{status.textContent='Gemma ищет общие темы. Обычно это занимает до минуты…';});status.textContent=data.message;if(data.created)window.location.reload();}
    catch(error){status.textContent=error.message||'Не удалось связаться с сервером.';}
    finally{button.disabled=false;form.removeAttribute('aria-busy');button.focus();}
  });
});
