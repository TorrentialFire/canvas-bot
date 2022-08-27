from dataclasses import dataclass
import asyncio
from datetime import date, datetime
import asyncpg

@dataclass
class CBotData():
    pool: asyncpg.pool.Pool
    
    @classmethod
    async def create(cls, host: str, database: str, user: str, password: str):
        pool = await asyncpg.create_pool(user=user, password=password, database=database, host=host)
        self = CBotData(pool)
        return self
    
    def __del__(self):
        asyncio.run(self.pool.close())

    # Creates the necessary tables and structures in the database for the bot's
    # data storage needs.
    # Thoughtful changes required here. There is currently no automated mechanism
    # to support changing the existing DB structure. Additive changes will
    # *probably* be fine, but modifying existing statements may lead to issues.
    async def initialize_database(self):

        # Acquire a connection to the database
        async with self.pool.acquire() as conn:

            # Create the test table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS assignment(
                    id serial PRIMARY KEY,
                    canvas_id int UNIQUE NOT NULL,
                    course_id int NOT NULL,
                    assignment_name text NOT NULL,
                    description text,
                    html_url text NOT NULL,
                    created_at date NOT NULL,
                    unlock_at date NOT NULL,
                    due_at date NOT NULL
                );

                CREATE TABLE IF NOT EXISTS submission(
                    id serial PRIMARY KEY,
                    canvas_id int NOT NULL,
                    assignment_id int NOT NULL,
                    attempt int NOT NULL,
                    late boolean NOT NULL,
                    submitted_at date NOT NULL,
                    CONSTRAINT fk_assignment
                        FOREIGN KEY(assignment_id)
                            REFERENCES assignment(canvas_id)
                );
            ''')


    async def get_assignments(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch('SELECT * FROM assignment')

    async def get_assignments(self, course_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetch('SELECT * FROM assignment WHERE course_id = $1', course_id)

    async def new_assignment(self, canvas_id: int, course_id: int, assignment_name: str, description: str, html_url: str, created_at: datetime, unlock_at: datetime, due_at: datetime):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO assignment(canvas_id, course_id, assignment_name, description, html_url, created_at, unlock_at, due_at)
                VALUES($1, $2, $3, $4, $5, $6, $7, $8);
            ''', canvas_id, course_id, assignment_name, description, html_url, created_at, unlock_at, due_at)

    async def get_submissions(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch('SELECT * FROM submission')

    async def get_submissions(self, assignment_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetch('SELECT * FROM submission WHERE assignment_id = $1', assignment_id)

    async def new_submission(self, canvas_id: int, assignment_id: int, attempt: int, late: bool, submitted_at: datetime):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO submission(canvas_id, assignment_id, attempt, late, submitted_at)
                VALUES($1, $2, $3, $4, $5)
            ''', canvas_id, assignment_id, attempt, late, submitted_at)