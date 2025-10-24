BEGIN;
    SELECT plan(3);
    SELECT fail('simple fail');
    SELECT pass('simple pass');
    SELECT * FROM finish();
ROLLBACK;