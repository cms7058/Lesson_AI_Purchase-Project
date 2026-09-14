import json

from fastapi.testclient import TestClient
from test_supplier_portal import (
    scenario as scenario,  # noqa: PLC0414 -- expose shared pytest fixture
)

from app.api.routes import supplier_execution
from app.main import app

client = TestClient(app)
H = {"X-User-Role":"admin"}


def order_for(supplier):
    result = client.post('/api/v1/orders',headers=H,json={"supplier_id":supplier['code'],"supplier_name":supplier['name'],"factory_code":"F1","lines":[{"material_code":"EXEC-M","material_name":"执行测试物料","quantity":5,"unit":"件","unit_price":20}]})
    assert result.status_code == 201, result.text
    order = result.json()
    client.patch('/api/v1/orders/'+order['id'],headers=H,json={"status":"sent"})
    return order


def test_supplier_delivery_scope_capacity_and_receipt_workflow(scenario):
    _, suppliers, sessions = scenario
    order = order_for(suppliers[0])
    url = '/api/v1/supplier/orders'
    assert client.get(url).status_code == 401
    assert client.get(url,headers=sessions[0]).json()['total'] == 1
    assert client.get(url,headers=sessions[1]).json()['total'] == 0
    assert client.post(url+'/'+order['id']+'/confirm',headers=sessions[1]).status_code == 404
    assert client.post(url+'/'+order['id']+'/confirm',headers=sessions[0]).status_code == 200
    assert client.post(url+'/'+order['id']+'/confirm',headers=sessions[0]).status_code == 409
    data={"order_id":order['id'],"material_code":"EXEC-M","quantity":3,"carrier":"测试物流","tracking_no":"TRACK-1","shipped_date":"2026-09-04","expected_date":"2026-09-05"}
    assert client.post('/api/v1/supplier/deliveries',headers=sessions[1],json=data).status_code == 404
    result=client.post('/api/v1/supplier/deliveries',headers=sessions[0],json=data)
    assert result.status_code == 201,result.text
    delivery=result.json()
    assert delivery['status']=='in_transit'
    assert client.post('/api/v1/supplier/deliveries',headers=sessions[0],json=data).status_code==409
    assert client.get('/api/v1/supplier/deliveries',headers=sessions[1]).json()['total']==0
    assert client.delete('/api/v1/receipts/'+delivery['receipt_id'],headers=H).status_code==409
    assert client.post('/api/v1/receipts/'+delivery['receipt_id']+'/confirm',headers=H).status_code==200
    assert client.delete('/api/v1/supplier/deliveries/'+delivery['id'],headers=sessions[0]).status_code==409
    assert client.get('/api/v1/supplier/deliveries',headers=sessions[0]).json()['items'][0]['status']=='received'
    assert client.post('/api/v1/inspections',headers=H,json={"receipt_id":delivery['receipt_id'],"inspected_quantity":3,"accepted_quantity":3,"rejected_quantity":0}).status_code==201
    assert client.get(url,headers=sessions[0]).json()['items'][0]['status']=='partially_delivered'
    second=client.post('/api/v1/supplier/deliveries',headers=sessions[0],json={**data,'quantity':2,'tracking_no':'TRACK-2'}).json()
    assert client.delete('/api/v1/supplier/deliveries/'+second['id'],headers=sessions[0]).status_code==204
    filters=json.dumps([{"field":"material_code","op":"eq","value":"NOT-MATCHED"}])
    assert client.get(url,headers=sessions[0],params={'filters':filters}).json()['total']==0


def test_invoice_upload_download_audit_scope_limits_and_review(scenario,monkeypatch,tmp_path):
    monkeypatch.setattr(supplier_execution,'FILES',tmp_path)
    _, suppliers, sessions=scenario
    order=order_for(suppliers[0])
    recon=client.post('/api/v1/reconciliations',headers=H,json={'order_id':order['id'],'amount':100}).json()
    client.post('/api/v1/reconciliations/'+recon['id']+'/confirm',headers=H)
    assert client.get('/api/v1/supplier/reconciliations',headers=sessions[0]).json()['total']==1
    assert client.get('/api/v1/supplier/reconciliations',headers=sessions[1]).json()['total']==0
    data={'reconciliation_id':recon['id'],'invoice_no':'EXEC-'+order['id'],'amount':'60','tax_amount':'6','invoice_date':'2026-09-04'}
    file={'file':('invoice.pdf',b'%PDF-1.4\n%%EOF','application/pdf')}
    url='/api/v1/supplier/invoices'
    assert client.post(url,headers=sessions[1],data=data,files=file).status_code==404
    assert client.post(url,headers=sessions[0],data=data,files={'file':('bad.pdf',b'not a pdf')}).status_code==422
    result=client.post(url,headers=sessions[0],data=data,files=file)
    assert result.status_code==201,result.text
    invoice=result.json()
    assert invoice['status']=='received'
    assert client.get(url,headers=sessions[1]).json()['total']==0
    assert client.get(url+'/'+invoice['id']+'/file',headers=sessions[1]).status_code==404
    assert client.get(url+'/'+invoice['id']+'/file',headers=sessions[0]).content.startswith(b'%PDF-')
    assert client.get('/api/v1/invoices/'+invoice['id']+'/file',headers=H).status_code==200
    assert client.get('/api/v1/invoices/'+invoice['id']+'/file',headers={'X-User-Role':'analyst'}).status_code==403
    assert client.post(url,headers=sessions[0],data={**data,'invoice_no':data['invoice_no']+'-OVER'},files=file).status_code==409
    assert client.post(url,headers=sessions[0],data={**data,'amount':'10'},files=file).status_code==409
    assert len(list(tmp_path.iterdir()))==1
    internal=client.get('/api/v1/invoices',headers=H,params={'filters':json.dumps([{'field':'invoice_no','op':'eq','value':data['invoice_no']}])}).json()['items'][0]
    assert internal['attachment_name']=='invoice.pdf'
    assert client.patch('/api/v1/invoices/'+invoice['id']+'/status',headers=H,json={'status':'verified'}).status_code==200
    assert client.get(url,headers=sessions[0]).json()['items'][0]['status']=='verified'
    assert client.delete(url+'/'+invoice['id'],headers=sessions[0]).status_code==409


def test_invoice_withdraw_and_reupload(scenario,monkeypatch,tmp_path):
    monkeypatch.setattr(supplier_execution,'FILES',tmp_path)
    _,suppliers,sessions=scenario
    order=order_for(suppliers[0])
    recon=client.post('/api/v1/reconciliations',headers=H,json={'order_id':order['id'],'amount':100}).json()
    client.post('/api/v1/reconciliations/'+recon['id']+'/confirm',headers=H)
    data={'reconciliation_id':recon['id'],'invoice_no':'WITHDRAW-'+order['id'],'amount':'10','tax_amount':'1','invoice_date':'2026-09-04'}
    r=client.post('/api/v1/supplier/invoices',headers=sessions[0],data=data,files={'file':('i.pdf',b'%PDF-1.4\n%%EOF')})
    assert r.status_code==201,r.text
    assert client.delete('/api/v1/supplier/invoices/'+r.json()['id'],headers=sessions[0]).status_code==204
    assert not list(tmp_path.iterdir())
