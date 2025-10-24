CREATE SCHEMA mytests;
CREATE TABLE pets (
    id SERIAL PRIMARY KEY,
    animal TEXT,
    name TEXT
);


CREATE OR REPLACE FUNCTION mytests.setup()
RETURNS SETOF TEXT AS
$func$
BEGIN
    INSERT INTO pets (name, animal)
    VALUES
        ('Bailey', 'cat'),
        ('Romulus', 'cat'),
        ('Florence', 'dog');
    RETURN NEXT is((SELECT count(*) FROM pets), 3::bigint, 'Should have 3 pets');
END;
$func$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION mytests.test_two_cats()
RETURNS SETOF TEXT AS
$func$
BEGIN
    RETURN QUERY
    SELECT set_eq(
        $$SELECT name FROM pets WHERE animal = 'cat'$$,
        ARRAY['Bailey', 'Romulus'],
        'pets table should contain two cats.' );
END;
$func$ LANGUAGE plpgsql;


-- CREATE OR REPLACE FUNCTION mytests.test_two_cats()
-- RETURNS SETOF TEXT AS
-- $func$
--     SELECT set_eq(
--         $$SELECT name FROM pets WHERE animal = 'cat'$$,
--         ARRAY['Bailey', 'Romulus'],
--         'pets table should contain two cats.' );
-- $func$ LANGUAGE sql;


CREATE OR REPLACE FUNCTION mytests.teardown()
RETURNS SETOF TEXT AS
$func$
BEGIN
    TRUNCATE pets;
    RETURN NEXT diag('teardown done');
END;
$func$ LANGUAGE plpgsql;