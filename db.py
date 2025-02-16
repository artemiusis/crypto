import sqlite3

class Database:
    def __init__(self,db_file):
        self.connection = sqlite3.connect(db_file)
        self.cursor =self.connection.cursor()
    
    def user_exists(self, user_id):
        with self.connection:
            result = self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchall()
            return bool(len(result))
    
    def add_user(self,user_id):
        with self.connection:
            return self.cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))

    def add_signal(self, user_id, signal_name):
        with self.connection:
            return self.cursor.execute("INSERT INTO signals (user_id, signal_name) VALUES (?, ?)", (user_id,signal_name,))
    def delete_signal(self,user_id,signal_name):
        with self.connection:
            return self.cursor.execute("DELETE FROM signals WHERE user_id = ? AND signal_name = ?", (user_id,signal_name,))
    def select_signals(self, user_id):
        with self.connection:
            # Виконуємо запит для отримання лише назв сигналів для користувача
            self.cursor.execute("SELECT signal_name FROM signals WHERE user_id = ?", (user_id,))
            signal_names = self.cursor.fetchall()  # Отримуємо всі результати
        
        # Повертаємо список назв сигналів
        return [signal[0] for signal in signal_names]


    def select_signal_info(self, user_id, signal_name):
        with self.connection:
        # Виконуємо запит для отримання всіх сигналів користувача
            self.cursor.execute("SELECT signal_name, growth, age, market_cap, volume, liquidity, boosts, volume_growth, time_growth FROM signals WHERE user_id = ? AND signal_name = ?", (user_id,signal_name))
            signal = self.cursor.fetchone()  # Отримуємо всі результати
        
        # Повертаємо список сигналів
        return signal
    def update_signal_price_growth(self, user_id, price_growth):
    # Спочатку перевіряємо всі сигнали користувача, де немає price_growth
        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ?", (user_id,))
            signal_to_update = self.cursor.fetchall()[-1]

 
            signal_id = signal_to_update[0]  # Отримуємо id сигналу
            self.cursor.execute("UPDATE signals SET growth = ? WHERE id = ?", (price_growth, signal_id))

    def update_signal_age(self, user_id, age):

        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ?", (user_id,))
            signal_to_update = self.cursor.fetchall()[-1]

 
            signal_id = signal_to_update[0]  # Отримуємо id сигналу
            self.cursor.execute("UPDATE signals SET age = ? WHERE id = ?", (age, signal_id))
            
    def update_signal_cap(self, user_id, cap):

        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ?", (user_id,))
            signal_to_update = self.cursor.fetchall()[-1]

 
            signal_id = signal_to_update[0]  # Отримуємо id сигналу
            self.cursor.execute("UPDATE signals SET market_cap = ? WHERE id = ?", (cap, signal_id))

    def update_signal_volume(self, user_id, volume):

        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ?", (user_id,))
            signal_to_update = self.cursor.fetchall()[-1]

 
            signal_id = signal_to_update[0]  # Отримуємо id сигналу
            self.cursor.execute("UPDATE signals SET volume = ? WHERE id = ?", (volume, signal_id))
    def update_signal_liquidity(self, user_id, liquidity):

        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ?", (user_id,))
            signal_to_update = self.cursor.fetchall()[-1]
            
 
            signal_id = signal_to_update[0]  # Отримуємо id сигналу
            self.cursor.execute("UPDATE signals SET liquidity = ? WHERE id = ?", (liquidity, signal_id))
    def update_signal_boosts(self, user_id, boosts):

        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ?", (user_id,))
            signal_to_update = self.cursor.fetchall()[-1]

 
            signal_id = signal_to_update[0]  # Отримуємо id сигналу
            self.cursor.execute("UPDATE signals SET boosts = ? WHERE id = ?", (boosts, signal_id))    
    def update_signal_volume_growth(self, user_id, volume, time):

        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ?", (user_id,))
            signal_to_update = self.cursor.fetchall()[-1]

 
            signal_id = signal_to_update[0]  # Отримуємо id сигналу
            self.cursor.execute("UPDATE signals SET volume_growth = ?, time_growth = ? WHERE id = ?", (volume, time, signal_id)) 
    def change_signal_status(self, user_id, name, status):
        with self.connection:
            self.cursor.execute("SELECT id FROM signals WHERE user_id = ? AND signal_name = ?", (user_id, name))
            signal_to_update = self.cursor.fetchone()[0]

 
          
            self.cursor.execute("UPDATE signals SET active = ? WHERE id = ?", (status, signal_to_update))
    def check_signal_status(self, user_id, name):
        with self.connection:
            self.cursor.execute("SELECT active FROM signals WHERE user_id = ? AND signal_name = ?", (user_id, name))
            row = self.cursor.fetchone()
            if row:
                status = bool(row[0])
            else:
                status = 0
            return status
    def update_signal_success(self, user_id, signal_name):

        with self.connection:

            self.cursor.execute("SELECT success FROM signals WHERE user_id = ? AND signal_name = ?", (user_id,signal_name,))
            success = self.cursor.fetchall()[-1]
            success +=1
            self.cursor.execute("UPDATE signals SET success = ? WHERE id = ? AND signal_name = ?", (success, user_id, signal_name)) 
    def update_signal_unsuccess(self, user_id, signal_name):

        with self.connection:

            self.cursor.execute("SELECT unsuccess FROM signals WHERE user_id = ? AND signal_name = ?", (user_id,signal_name,))
            unsuccess = self.cursor.fetchall()[-1]
            unsuccess +=1
            self.cursor.execute("UPDATE signals SET unsuccess = ? WHERE id = ? AND signal_name = ?", (unsuccess, user_id, signal_name))    
    def check_signal_success(self, user_id, signal_name):

        with self.connection:

            self.cursor.execute("SELECT success FROM signals WHERE user_id = ? AND signal_name = ?", (user_id,signal_name,))
            success = self.cursor.fetchall()[-1]
            return success
    def check_signal_unsuccess(self, user_id, signal_name):

        with self.connection:

            self.cursor.execute("SELECT success FROM signals WHERE user_id = ? AND signal_name = ?", (user_id,signal_name,))
            unsuccess = self.cursor.fetchall()[-1]
            return unsuccess
