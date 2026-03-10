fetch("/wallet/")
.then(res=>res.json())
.then(data=>{

document.getElementById("balance").innerText=data.balance

document.getElementById("recharge").innerText=data.recharge

document.getElementById("income").innerText=data.income

})