import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizeApiOrigin} from '../web/api-config.mjs';

test('accepts public HTTPS origin and local HTTP only from HTTP pages',()=>{
  assert.equal(normalizeApiOrigin(' https://api.example.com/ '),'https://api.example.com');
  assert.equal(normalizeApiOrigin('http://127.0.0.1:8000','http:'),'http://127.0.0.1:8000');
});
test('rejects mixed content, arbitrary schemes, paths and credentials',()=>{
  for(const url of ['http://127.0.0.1:8000','http://api.example.com','javascript:alert(1)','https://api.example.com/api','https://a:b@api.example.com','https://api.example.com/?key=x'])assert.throws(()=>normalizeApiOrigin(url));
});
